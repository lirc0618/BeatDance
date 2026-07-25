from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import numpy as np

from ..schemas import PauseInsight, Tutorial
from .diagnosis import ActionRegistry
from .video import probe_video

TARGET_VIEWS = ("背面跟练", "慢速分拍", "局部特写")


class PauseCoach:
    """Read one real Feed window and turn it into an explanation and reference."""

    def __init__(self, registry: ActionRegistry, feed_dir: Path, contexts_dir: Path):
        self.registry = registry
        self.feed_dir = feed_dir.resolve()
        self.contexts_dir = contexts_dir
        contexts_dir.mkdir(parents=True, exist_ok=True)

    def explain(self, action_id: str, timestamp_seconds: float) -> PauseInsight:
        action = self.registry.get(action_id)
        feed_path = self.feed_path(action_id)
        duration_seconds = probe_video(feed_path).duration_seconds
        if timestamp_seconds < 0 or timestamp_seconds > duration_seconds:
            raise ValueError("暂停时间点必须位于视频时长范围内")

        context_start = max(0.0, timestamp_seconds - 1.5)
        context_end = min(duration_seconds, timestamp_seconds + 1.5)
        observed_motion, sampled_frames = self._observe_motion(
            feed_path,
            context_start,
            context_end,
        )
        progress = timestamp_seconds / duration_seconds
        guide = self._guide_for_progress(action, progress)
        candidates = self.registry.search_tutorials(
            action_id,
            str(guide["metric"]),
            str(guide["body_part"]),
            focus=guide["suggested_focus"],
            limit=10,
        )

        return PauseInsight(
            action_id=action_id,
            timestamp_seconds=round(timestamp_seconds, 2),
            feed_duration_seconds=round(duration_seconds, 2),
            context_start_seconds=round(context_start, 2),
            context_end_seconds=round(context_end, 2),
            phase=str(guide["phase"]),
            likely_stuck_at=self._plain_problem(guide),
            watch_for=(f"别一口气看全身，今天只抓一件事：{guide['watch_for']} {observed_motion}"),
            observed_motion=observed_motion,
            sampled_frame_count=sampled_frames,
            suggested_focus=guide["suggested_focus"],
            search_results=self._ordered_views(candidates),
        )

    def feed_path(self, action_id: str) -> Path:
        action = self.registry.get(action_id)
        media_path = urlsplit(str(action.get("feed_video_url", ""))).path
        filename = Path(media_path).name
        if not filename:
            raise FileNotFoundError(f"动作 {action_id} 未配置 Feed 视频")
        path = (self.feed_dir / filename).resolve()
        if path.parent != self.feed_dir or not path.is_file():
            raise FileNotFoundError(f"动作 {action_id} 的 Feed 视频不存在")
        return path

    def extract_context(self, action_id: str, insight: PauseInsight) -> Path:
        start_ms = round(insight.context_start_seconds * 1000)
        end_ms = round(insight.context_end_seconds * 1000)
        target = self.contexts_dir / f"{action_id}-{start_ms}-{end_ms}.mp4"
        if target.exists() and target.stat().st_size > 0:
            return target

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("未找到 ffmpeg，无法截取暂停上下文")
        pending = target.with_name(f".{target.stem}-{uuid4().hex}.pending.mp4")
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    str(insight.context_start_seconds),
                    "-t",
                    str(insight.context_end_seconds - insight.context_start_seconds),
                    "-i",
                    str(self.feed_path(action_id)),
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
                    str(pending),
                ],
                check=True,
                timeout=90,
            )
            probe_video(pending)
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)
        return target

    @staticmethod
    def _observe_motion(path: Path, start: float, end: float) -> tuple[str, int]:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError("无法读取 Feed 暂停上下文")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        sample_step = max(1, round(fps / 10.0))
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        previous = None
        differences: list[float] = []
        sampled_frames = 0
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            current_time = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            if current_time > end:
                break
            if frame_index % sample_step == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, (96, 54))
                if previous is not None:
                    differences.append(float(np.mean(cv2.absdiff(gray, previous))) / 255.0)
                previous = gray
                sampled_frames += 1
            frame_index += 1
        cap.release()
        if sampled_frames < 2:
            raise ValueError("暂停点附近没有足够视频帧")
        intensity = float(np.mean(differences)) if differences else 0.0
        if intensity < 0.015:
            level = "这几秒像按了暂停键，正适合照着摆造型。"
        elif intensity < 0.045:
            level = "这几秒正在“换挡”，开 0.5 倍最容易看懂。"
        else:
            level = "这几秒手脚有点忙，先只盯一个部位，别让眼睛加班。"
        return level, sampled_frames

    @staticmethod
    def _plain_problem(guide: dict[str, Any]) -> str:
        phase = str(guide["phase"])
        body_part = str(guide["body_part"])
        metric = str(guide["metric"])
        if metric == "timing":
            return f"{phase}这里，{body_part}和拍子没对上暗号，像两个人抢着说话。"
        if metric == "trajectory":
            return f"{phase}这里，{body_part}的导航容易走偏。不是不会，是眼睛一下看太多了。"
        return f"{phase}这里，{body_part}的“定格照”容易没摆到位，就差最后一下。"

    @staticmethod
    def _guide_for_progress(action: dict[str, Any], progress: float) -> dict[str, Any]:
        guides = action.get("pause_guides", [])
        if not guides:
            return {
                "until_ratio": 1.0,
                "phase": "最容易卡壳的地方",
                "likely_stuck_at": action["description"],
                "watch_for": "先看谁最先动，再看它最后停在哪。",
                "suggested_focus": "auto",
                "metric": "timing",
                "body_part": "躯干",
            }
        return next(
            (guide for guide in guides if progress <= float(guide["until_ratio"])),
            guides[-1],
        )

    @staticmethod
    def _ordered_views(candidates: list[Tutorial]) -> list[Tutorial]:
        by_view: dict[str, Tutorial] = {}
        for item in candidates:
            by_view.setdefault(item.view_type, item)
        return [by_view[view] for view in TARGET_VIEWS if view in by_view]
