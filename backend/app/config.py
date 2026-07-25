from __future__ import annotations

import json
import re
import shutil
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict

from .file_lock import catalog_transaction


class Settings(BaseSettings):
    app_name: str = "对拍 API"
    api_prefix: str = "/api/v1"
    data_dir: Path = Path("/data")
    h5_dir: Path = Path("/app/h5")
    feed_dir: Path = Path("/data/feeds")
    seed_feed_dir: Path = Path("/app/assets/samples/open_sources")
    max_video_seconds: float = 8.0
    min_video_seconds: float = 3.0
    max_upload_mb: int = 40
    max_feed_upload_mb: int = 200
    max_feed_seconds: float = 600
    max_feed_actions: int = 50
    max_feed_storage_mb: int = 5000
    max_concurrent_feed_imports: int = 1
    target_fps: float = 15.0
    pose_model_complexity: int = 1
    pose_min_detection_confidence: float = 0.5
    pose_min_tracking_confidence: float = 0.5
    min_pose_coverage: float = 0.65
    keep_original_video: bool = False
    admin_token: str = "change-me"
    allow_insecure_admin_token: bool = False

    # 火山方舟 / 豆包。ARK_MODEL 填模型推理接入点 ID。
    ark_api_key: str | None = None
    ark_model: str | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_timeout_seconds: float = 8.0
    ark_send_images: bool = True

    public_base_url: str = ""
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def references_dir(self) -> Path:
        return self.data_dir / "references"

    @property
    def results_dir(self) -> Path:
        return self.data_dir / "results"

    @property
    def visualizations_dir(self) -> Path:
        return self.data_dir / "visualizations"

    @property
    def comparison_videos_dir(self) -> Path:
        return self.data_dir / "comparison_videos"

    @property
    def pause_contexts_dir(self) -> Path:
        return self.data_dir / "pause_contexts"

    @property
    def action_registry_path(self) -> Path:
        override = self.data_dir / "actions.json"
        if override.exists():
            return override
        return self.built_in_action_registry_path

    @property
    def built_in_action_registry_path(self) -> Path:
        return Path(__file__).parent / "data" / "actions.json"

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.feed_dir,
            self.uploads_dir,
            self.references_dir,
            self.results_dir,
            self.visualizations_dir,
            self.comparison_videos_dir,
            self.pause_contexts_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def admin_mutations_enabled(self) -> bool:
        token = self.admin_token.strip()
        if self.allow_insecure_admin_token:
            return bool(token)
        placeholders = {
            "change-me",
            "replace-with-a-long-random-secret",
        }
        return self.admin_token == token and len(token) >= 24 and token not in placeholders

    def bootstrap_runtime_catalog(self) -> None:
        """Seed the persistent catalog and bundled feeds on first startup."""

        with catalog_transaction(self.data_dir):
            self._bootstrap_runtime_catalog()

    def _bootstrap_runtime_catalog(self) -> None:
        runtime_registry = self.data_dir / "actions.json"
        if not runtime_registry.exists():
            self._atomic_copy(self.built_in_action_registry_path, runtime_registry)
        payload = json.loads(runtime_registry.read_text(encoding="utf-8"))
        for action in payload["actions"]:
            filename = Path(str(action.get("feed_video_url", ""))).name
            if not filename:
                continue
            source = self.seed_feed_dir / filename
            target = self.feed_dir / filename
            if not target.exists() and source.is_file():
                self._atomic_copy(source, target)
        attribution = self.seed_feed_dir / "ATTRIBUTION.md"
        if attribution.is_file() and not (self.feed_dir / attribution.name).exists():
            self._atomic_copy(attribution, self.feed_dir / attribution.name)
        self._reconcile_generated_files(payload)

    def _reconcile_generated_files(self, payload: dict) -> None:
        """Remove interrupted and superseded imports after a clean startup."""

        active: set[Path] = set()
        for action in payload["actions"]:
            feed_name = Path(str(action.get("feed_video_url", ""))).name
            if feed_name:
                active.add(self.feed_dir / feed_name)
            manifest_name = Path(
                str(
                    action.get(
                        "reference_manifest",
                        f"{action['id']}.current.json",
                    )
                )
            ).name
            manifest_path = self.references_dir / manifest_name
            active.add(manifest_path)
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for key in ("video", "sequence"):
                filename = Path(str(manifest.get(key, ""))).name
                if filename:
                    active.add(self.references_dir / filename)

        generated = re.compile(
            r"^[a-z][a-z0-9_-]{0,63}-[0-9a-f]{32}"
            r"\.(?:mp4|npz|current\.json)$"
        )
        for root in (self.feed_dir, self.references_dir):
            for path in root.iterdir():
                is_interrupted = path.name.startswith(".") and ".pending" in path.name
                is_orphan = generated.fullmatch(path.name) and path not in active
                if is_interrupted or is_orphan:
                    path.unlink(missing_ok=True)

    @staticmethod
    def _atomic_copy(source: Path, target: Path) -> None:
        pending = target.with_name(f".{target.name}-{uuid4().hex}.pending")
        try:
            shutil.copy2(source, pending)
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    settings.bootstrap_runtime_catalog()
    return settings
