from __future__ import annotations

import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict

from .file_lock import catalog_transaction


class Settings(BaseSettings):
    app_name: str = "对拍（BeatDance）API"
    api_prefix: str = "/api/v1"
    data_dir: Path = Path("/data")
    h5_dir: Path = Path("/app/h5")
    feed_dir: Path = Path("/data/feeds")
    seed_feed_dir: Path = Path("/app/assets/samples/open_sources")
    seed_reference_dir: Path = Path("/app/assets/references")
    tutorial_assets_dir: Path = Path("assets/tutorials")
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
    action_match_max_cost: float = 2.0
    action_match_alternative_ratio: float = 0.65
    keep_original_video: bool = False
    admin_token: str = "change-me"
    allow_insecure_admin_token: bool = False

    # 火山方舟 / 豆包。ARK_MODEL 填模型推理接入点 ID。
    ark_api_key: str | None = None
    ark_model: str | None = None
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_timeout_seconds: float = 8.0
    ark_send_images: bool = True

    # 阿里云百炼 / Qwen。只用于管理员参考素材的离线教学计划，不处理用户模仿视频。
    dashscope_api_key: str | None = None
    qwen_model: str = "qwen3.7-plus"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_timeout_seconds: float = 30.0
    qwen_send_images: bool = True
    qwen_max_frames: int = 12

    # 抖音开放平台视频搜索。可直接填短期 ACCESS_TOKEN，或配置 key/secret 自动换取。
    douyin_access_token: str | None = None
    douyin_client_key: str | None = None
    douyin_client_secret: str | None = None
    douyin_token_url: str = "https://open.douyin.com/oauth/client_token/"
    douyin_search_url: str = "https://open.douyin.com/dy_open_api/v2/search/video/"
    douyin_device_id: int = 20260725
    douyin_timeout_seconds: float = 8.0
    douyin_search_cache_seconds: float = 120.0
    douyin_search_max_per_minute: int = 30

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
    def covers_dir(self) -> Path:
        return self.data_dir / "covers"

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
    def teaching_plans_dir(self) -> Path:
        return self.data_dir / "teaching_plans"

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
            self.covers_dir,
            self.visualizations_dir,
            self.comparison_videos_dir,
            self.pause_contexts_dir,
            self.teaching_plans_dir,
            self.tutorial_assets_dir,
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
        built_in = json.loads(
            self.built_in_action_registry_path.read_text(encoding="utf-8")
        )
        if not runtime_registry.exists():
            self._atomic_copy(self.built_in_action_registry_path, runtime_registry)
        payload = json.loads(runtime_registry.read_text(encoding="utf-8"))
        built_in_by_id = {
            str(action["id"]): action for action in built_in["actions"]
        }
        active_ids = {str(action["id"]) for action in payload["actions"]}
        catalog_changed = False
        if (
            "jazz_demo" not in active_ids
            and "library_breakdance_2_step" in active_ids
        ):
            payload = {
                **payload,
                "actions": [
                    built_in_by_id["jazz_demo"]
                    if action["id"] == "library_breakdance_2_step"
                    else action
                    for action in payload["actions"]
                ],
            }
            active_ids.remove("library_breakdance_2_step")
            active_ids.add("jazz_demo")
            catalog_changed = True
        partially_migrated_jazz = any(
            action.get("id") == "jazz_demo"
            and (
                Path(str(action.get("reference_manifest", ""))).name.startswith(
                    "library_breakdance_2_step-"
                )
                or Path(str(action.get("feed_video_url", ""))).name.startswith(
                    "library_breakdance_2_step-"
                )
            )
            for action in payload["actions"]
        )
        if partially_migrated_jazz:
            payload = {
                **payload,
                "actions": [
                    built_in_by_id["jazz_demo"]
                    if action.get("id") == "jazz_demo"
                    else action
                    for action in payload["actions"]
                ],
            }
            catalog_changed = True
        missing = [
            action
            for action in built_in["actions"]
            if str(action["id"]) not in active_ids
        ]
        if missing:
            payload = {
                **payload,
                "actions": [*payload["actions"], *missing],
            }
            catalog_changed = True
        if catalog_changed:
            self._atomic_write_json(runtime_registry, payload)
        for action in payload["actions"]:
            filename = Path(str(action.get("feed_video_url", ""))).name
            if not filename:
                continue
            source = self.seed_feed_dir / filename
            target = self.feed_dir / filename
            if not target.exists() and source.is_file():
                self._atomic_copy(source, target)
            if self._ensure_feed_cover(action, target):
                catalog_changed = True
            self._seed_reference(action)
        if catalog_changed:
            self._atomic_write_json(runtime_registry, payload)
        attribution = self.seed_feed_dir / "ATTRIBUTION.md"
        if attribution.is_file() and not (self.feed_dir / attribution.name).exists():
            self._atomic_copy(attribution, self.feed_dir / attribution.name)
        self._reconcile_generated_files(payload)

    def _seed_reference(self, action: dict) -> None:
        manifest_name = Path(
            str(action.get("reference_manifest", f"{action['id']}.current.json"))
        ).name
        source_manifest = self.seed_reference_dir / manifest_name
        target_manifest = self.references_dir / manifest_name
        if not source_manifest.is_file():
            return
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        for key in ("video", "sequence"):
            filename = Path(str(manifest[key])).name
            source = self.seed_reference_dir / filename
            target = self.references_dir / filename
            if source.is_file() and not target.exists():
                self._atomic_copy(source, target)
        if not target_manifest.exists():
            self._atomic_copy(source_manifest, target_manifest)

    def _ensure_feed_cover(self, action: dict, feed_path: Path) -> bool:
        """Generate a stable preview frame without changing the source aspect ratio."""

        if not feed_path.is_file():
            return False
        cover_name = f"{feed_path.stem}.jpg"
        cover_path = self.covers_dir / cover_name
        changed = action.get("cover_url") != f"/media/covers/{cover_name}"
        if not cover_path.is_file():
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                return False
            pending = cover_path.with_name(f".{cover_path.stem}-{uuid4().hex}.pending.jpg")
            try:
                subprocess.run(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-ss",
                        "0.5",
                        "-i",
                        str(feed_path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=w='min(960,iw)':h='min(960,ih)'"
                        ":force_original_aspect_ratio=decrease"
                        ":force_divisible_by=2:flags=lanczos",
                        "-q:v",
                        "3",
                        str(pending),
                    ],
                    check=True,
                    timeout=60,
                )
                pending.replace(cover_path)
            except (OSError, subprocess.SubprocessError):
                return False
            finally:
                pending.unlink(missing_ok=True)
        action["cover_url"] = f"/media/covers/{cover_name}"
        return changed

    def _reconcile_generated_files(self, payload: dict) -> None:
        """Remove interrupted and superseded imports after a clean startup."""

        active: set[Path] = set()
        for action in payload["actions"]:
            feed_name = Path(str(action.get("feed_video_url", ""))).name
            if feed_name:
                active.add(self.feed_dir / feed_name)
                active.add(self.covers_dir / f"{Path(feed_name).stem}.jpg")
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
            r"\.(?:mp4|npz|jpg|current\.json)$"
        )
        for root in (self.feed_dir, self.references_dir, self.covers_dir):
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

    @staticmethod
    def _atomic_write_json(target: Path, payload: dict) -> None:
        pending = target.with_name(f".{target.name}-{uuid4().hex}.pending")
        try:
            pending.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    settings.bootstrap_runtime_catalog()
    return settings
