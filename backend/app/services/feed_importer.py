from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..config import Settings
from ..file_lock import catalog_transaction
from .diagnosis import ActionRegistry
from .pose import extract_pose_sequence
from .video import VideoValidationError, probe_video

ACTION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
logger = logging.getLogger(__name__)


class FeedImportBusyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FeedImportSpec:
    action_id: str
    name: str
    pause_at_seconds: float | None = None
    description: str = ""
    feed_caption: str = ""
    creator: str = "自定义素材"
    focus: str = "auto"


@dataclass(frozen=True, slots=True)
class FeedImportResult:
    created: bool
    action: dict[str, Any]
    duration_seconds: float
    pose_coverage: float


class FeedImporter:
    """Publish one arbitrary Feed and everything required to analyze it."""

    def __init__(self, settings: Settings, registry: ActionRegistry):
        self.settings = settings
        self.registry = registry
        self.import_slots = threading.BoundedSemaphore(max(1, settings.max_concurrent_feed_imports))

    def import_video(
        self,
        source: Path,
        spec: FeedImportSpec,
    ) -> FeedImportResult:
        if not self.import_slots.acquire(blocking=False):
            raise FeedImportBusyError("已有视频正在导入，请稍后重试")
        try:
            return self._import_video(source, spec)
        finally:
            self.import_slots.release()

    def _import_video(
        self,
        source: Path,
        spec: FeedImportSpec,
    ) -> FeedImportResult:
        with catalog_transaction(self.settings.data_dir):
            return self._publish_video(source, spec)

    def _publish_video(
        self,
        source: Path,
        spec: FeedImportSpec,
    ) -> FeedImportResult:
        self._validate(source, spec)
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("未找到 ffmpeg，无法导入 Feed 视频")

        try:
            previous_action = self.registry.get(spec.action_id)
        except KeyError:
            previous_action = None
        nonce = uuid4().hex
        feed_target = self.settings.feed_dir / f"{spec.action_id}-{nonce}.mp4"
        reference_video = self.settings.references_dir / f"{spec.action_id}-{nonce}.mp4"
        reference_sequence = self.settings.references_dir / f"{spec.action_id}-{nonce}.npz"
        reference_manifest = self.settings.references_dir / f"{spec.action_id}-{nonce}.current.json"
        published = [
            feed_target,
            reference_video,
            reference_sequence,
            reference_manifest,
        ]
        try:
            self._transcode(ffmpeg, source, feed_target)
            metadata = probe_video(feed_target)
            if metadata.duration_seconds < 3:
                raise VideoValidationError(
                    f"Feed 视频至少需要 3 秒，当前约 {metadata.duration_seconds:.1f} 秒"
                )
            pause_at = (
                metadata.duration_seconds / 2 if spec.pause_at_seconds is None else spec.pause_at_seconds
            )
            if pause_at < 0 or pause_at > metadata.duration_seconds:
                raise VideoValidationError("参考时间点必须位于 Feed 视频时长范围内")

            clip_duration = min(5.0, metadata.duration_seconds)
            clip_start = min(
                max(0.0, pause_at - clip_duration / 2),
                metadata.duration_seconds - clip_duration,
            )
            self._clip(
                ffmpeg,
                feed_target,
                reference_video,
                clip_start,
                clip_duration,
            )
            pose = extract_pose_sequence(
                reference_video,
                target_fps=self.settings.target_fps,
                model_complexity=self.settings.pose_model_complexity,
                min_detection_confidence=self.settings.pose_min_detection_confidence,
                min_tracking_confidence=self.settings.pose_min_tracking_confidence,
            )
            if pose.coverage < self.settings.min_pose_coverage:
                raise VideoValidationError(
                    f"参考时间点附近人体覆盖率仅 {pose.coverage:.0%}，请换一个单人全身清晰的时间点"
                )
            self._save_pose(pose, reference_sequence)
            self._write_json(
                reference_manifest,
                {
                    "generation": nonce,
                    "video": reference_video.name,
                    "sequence": reference_sequence.name,
                },
            )
            if self._storage_bytes() > self.settings.max_feed_storage_mb * 1024 * 1024:
                raise VideoValidationError(
                    f"Feed 与参考素材总量不能超过 {self.settings.max_feed_storage_mb}MB"
                )
            action = self._action_payload(
                spec,
                duration_seconds=metadata.duration_seconds,
                feed_name=feed_target.name,
                reference_manifest=reference_manifest.name,
            )
            created = self.registry.replace_action(action)
            try:
                self._prune_old_generations(
                    spec.action_id,
                    current_action=action,
                    previous_action=previous_action,
                )
            except Exception:
                # The catalog is already committed. Cleanup is best effort and
                # must not send control into the rollback path below.
                logger.warning(
                    "Failed to prune old Feed generations for %s",
                    spec.action_id,
                    exc_info=True,
                )
            return FeedImportResult(
                created=created,
                action=action,
                duration_seconds=round(metadata.duration_seconds, 2),
                pose_coverage=pose.coverage,
            )
        except Exception:
            for path in published:
                path.unlink(missing_ok=True)
            raise

    def _validate(self, source: Path, spec: FeedImportSpec) -> None:
        if not source.is_file():
            raise FileNotFoundError(f"视频不存在：{source}")
        if not ACTION_ID.fullmatch(spec.action_id):
            raise ValueError("动作 ID 只能使用小写字母、数字、下划线或连字符")
        if not spec.name.strip():
            raise ValueError("动作名称不能为空")
        if spec.focus not in {"auto", "upper", "lower", "timing"}:
            raise ValueError("关注点必须是 auto、upper、lower 或 timing")
        if source.stat().st_size > self.settings.max_feed_upload_mb * 1024 * 1024:
            raise VideoValidationError(f"Feed 视频不能超过 {self.settings.max_feed_upload_mb}MB")
        metadata = probe_video(source)
        if metadata.duration_seconds < 3:
            raise VideoValidationError(f"Feed 视频至少需要 3 秒，当前约 {metadata.duration_seconds:.1f} 秒")
        if metadata.duration_seconds > self.settings.max_feed_seconds:
            raise VideoValidationError(f"Feed 视频不能超过 {self.settings.max_feed_seconds:g} 秒")
        action_exists = any(action["id"] == spec.action_id for action in self.registry.list())
        if not action_exists and len(self.registry.list()) >= self.settings.max_feed_actions:
            raise VideoValidationError(
                f"Feed 动作不能超过 {self.settings.max_feed_actions} 条；可使用已有 ID 替换"
            )

    def _storage_bytes(self) -> int:
        return sum(
            path.stat().st_size
            for root in (self.settings.feed_dir, self.settings.references_dir)
            for path in root.iterdir()
            if path.is_file()
        )

    def _prune_old_generations(
        self,
        action_id: str,
        *,
        current_action: dict[str, Any],
        previous_action: dict[str, Any] | None,
    ) -> None:
        """Keep the active and immediately previous generation for safe readers."""

        keep: set[Path] = set()
        for action in (current_action, previous_action):
            if not action:
                continue
            feed_name = Path(str(action.get("feed_video_url", ""))).name
            if feed_name:
                keep.add(self.settings.feed_dir / feed_name)
            manifest_name = Path(
                str(
                    action.get(
                        "reference_manifest",
                        f"{action['id']}.current.json",
                    )
                )
            ).name
            manifest_path = self.settings.references_dir / manifest_name
            keep.add(manifest_path)
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for key in ("video", "sequence"):
                filename = Path(str(manifest.get(key, ""))).name
                if filename:
                    keep.add(self.settings.references_dir / filename)

        generated = re.compile(
            rf"^{re.escape(action_id)}-[0-9a-f]{{32}}"
            r"\.(?:mp4|npz|current\.json)$"
        )
        for root in (self.settings.feed_dir, self.settings.references_dir):
            for path in root.iterdir():
                if path not in keep and generated.fullmatch(path.name):
                    try:
                        path.unlink()
                    except OSError:
                        # Cleanup must never invalidate a catalog entry already committed.
                        pass

    @staticmethod
    def _run_ffmpeg(command: list[str], target: Path) -> None:
        pending = target.with_name(f".{target.name}-{uuid4().hex}.pending.mp4")
        try:
            try:
                subprocess.run(
                    [*command, str(pending)],
                    check=True,
                    capture_output=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired as exc:
                raise VideoValidationError("视频处理超时，请压缩后重试") from exc
            except subprocess.CalledProcessError as exc:
                raise VideoValidationError("视频转码失败，请换用 MP4、MOV 或 WEBM 格式") from exc
            probe_video(pending)
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)

    def _transcode(self, ffmpeg: str, source: Path, target: Path) -> None:
        self._run_ffmpeg(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-an",
                "-vf",
                "scale=w='min(1280,iw)':h='min(1280,ih)'"
                ":force_original_aspect_ratio=decrease"
                ":force_divisible_by=2:flags=lanczos,fps=25",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ],
            target,
        )

    def _clip(
        self,
        ffmpeg: str,
        source: Path,
        target: Path,
        start: float,
        duration: float,
    ) -> None:
        self._run_ffmpeg(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-i",
                str(source),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
            ],
            target,
        )

    @staticmethod
    def _save_pose(pose, target: Path) -> None:
        pending = target.with_name(f".{target.name}-{uuid4().hex}.pending.npz")
        try:
            pose.save(pending)
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        pending = path.with_name(f".{path.name}-{uuid4().hex}.pending")
        try:
            pending.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)

    @staticmethod
    def _action_payload(
        spec: FeedImportSpec,
        *,
        duration_seconds: float,
        feed_name: str,
        reference_manifest: str,
    ) -> dict[str, Any]:
        body_part = {
            "upper": "右臂",
            "lower": "右腿",
            "timing": "躯干",
            "auto": "躯干",
        }[spec.focus]
        suggested_focus = spec.focus if spec.focus != "timing" else "timing"
        name = spec.name.strip()
        return {
            "id": spec.action_id,
            "name": name,
            "description": spec.description.strip() or "播放视频，停在动作衔接、方向或发力顺序没看懂的时刻。",
            "duration_hint": "上传 3–8 秒模仿",
            "cover_url": "",
            "reference_video_url": "",
            "reference_manifest": reference_manifest,
            "feed_caption": spec.feed_caption.strip() or f"{name} 到底怎么做？停在你没看懂的那一秒。",
            "creator": spec.creator.strip() or "自定义素材",
            "segment_label": f"{duration_seconds:.0f} 秒素材 · 任意暂停",
            "entry_copy": "定格学这一招",
            "feed_video_url": f"/media/feed/{feed_name}",
            "pause_guides": [
                {
                    "until_ratio": 0.34,
                    "phase": "动作进入",
                    "likely_stuck_at": "你停在动作进入段，常见难点是没有看清启动顺序。",
                    "watch_for": "先看哪个身体部位最先启动，再看重心何时跟上。",
                    "suggested_focus": suggested_focus,
                    "metric": "timing",
                    "body_part": body_part,
                },
                {
                    "until_ratio": 0.67,
                    "phase": "动作转换",
                    "likely_stuck_at": "你停在动作转换处，常见难点是方向和重心同时变化。",
                    "watch_for": "先追踪主要身体部位的路线，再看动作先后顺序。",
                    "suggested_focus": suggested_focus,
                    "metric": "trajectory",
                    "body_part": body_part,
                },
                {
                    "until_ratio": 1.0,
                    "phase": "动作完成",
                    "likely_stuck_at": "你停在动作完成段，常见难点是幅度或回位不清楚。",
                    "watch_for": "对比动作终点和起点，观察角度、落点与重心是否回正。",
                    "suggested_focus": suggested_focus,
                    "metric": "angle",
                    "body_part": body_part,
                },
            ],
            "tutorials": [
                {
                    "id": f"{spec.action_id}-back",
                    "title": "背面跟练：只看动作顺序",
                    "url": "",
                    "error_type": "timing",
                    "body_part": body_part,
                    "description": "换到背面视角，去掉左右镜像干扰。",
                    "view_type": "背面跟练",
                    "creator": "@动作搜索",
                    "clip_seconds": "12 秒",
                    "tags": [suggested_focus, "timing"],
                },
                {
                    "id": f"{spec.action_id}-slow",
                    "title": "0.5 倍分拍：看清启动与落位",
                    "url": "",
                    "error_type": "timing",
                    "body_part": body_part,
                    "description": "把连续动作拆开，逐拍观察发力顺序。",
                    "view_type": "慢速分拍",
                    "creator": "@动作搜索",
                    "clip_seconds": "15 秒",
                    "tags": [suggested_focus, "timing"],
                },
                {
                    "id": f"{spec.action_id}-detail",
                    "title": "局部特写：只追踪主要路线",
                    "url": "",
                    "error_type": "trajectory",
                    "body_part": body_part,
                    "description": "放大主要身体部位，观察移动方向和终点。",
                    "view_type": "局部特写",
                    "creator": "@动作搜索",
                    "clip_seconds": "10 秒",
                    "tags": [suggested_focus, "trajectory"],
                },
            ],
            "diagnosis": {
                "thresholds": {
                    "timing_seconds": 0.55,
                    "trajectory": 0.55,
                    "angle_degrees": 55.0,
                },
                "weights": {
                    "timing": 1.05,
                    "trajectory": 1.0,
                    "angle": 0.95,
                },
                "aligned_threshold": 0.22,
            },
        }
