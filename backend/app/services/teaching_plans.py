from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import cv2
import httpx
import numpy as np

from ..config import Settings
from ..schemas import (
    FocusKind,
    TeachingPlan,
    TeachingPlanProvenance,
    TeachingSegment,
)
from .features import normalize_pose
from .pose import PoseSequence

ACTION_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TeachingPlanSource:
    action_id: str
    action_name: str
    reference_video: Path
    pose: PoseSequence
    source_hash: str
    source_start_seconds: float
    source_end_seconds: float
    default_focus: FocusKind = "auto"


def build_teaching_plan_source(
    *,
    action_id: str,
    action_name: str,
    reference_video: Path,
    pose: PoseSequence,
    source_start_seconds: float,
    default_focus: FocusKind,
) -> TeachingPlanSource:
    digest = hashlib.sha256()
    with reference_video.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return TeachingPlanSource(
        action_id=action_id,
        action_name=action_name,
        reference_video=reference_video,
        pose=pose,
        source_hash=digest.hexdigest(),
        source_start_seconds=source_start_seconds,
        source_end_seconds=source_start_seconds + pose.duration_seconds,
        default_focus=default_focus,
    )


class TeachingPlanGenerator(Protocol):
    @property
    def configured(self) -> bool: ...

    def generate(self, source: TeachingPlanSource) -> TeachingPlan: ...


class QwenTeachingPlanGenerator:
    """Generate a typed teaching plan from an authorized reference clip."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.settings.dashscope_api_key and self.settings.qwen_model)

    def generate(self, source: TeachingPlanSource) -> TeachingPlan:
        if not self.configured:
            raise RuntimeError("Qwen 教学计划未配置")
        text_prompt = self._prompt(source)
        user_content: Any = text_prompt
        if self.settings.qwen_send_images:
            frame_urls = self._reference_frame_urls(source.reference_video)
            if frame_urls:
                user_content = [
                    {"type": "video", "video": frame_urls},
                    {"type": "text", "text": text_prompt},
                ]
        payload = {
            "model": self.settings.qwen_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是动作教学策划，只分析管理员提供的参考动作。"
                        "输出严格 JSON，不评价用户，不生成分数。"
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 1800,
            "enable_thinking": False,
        }
        headers = {"Authorization": f"Bearer {self.settings.dashscope_api_key}"}
        client_kwargs: dict[str, Any] = {
            "timeout": self.settings.qwen_timeout_seconds,
        }
        if self.transport is not None:
            client_kwargs["transport"] = self.transport
        with httpx.Client(**client_kwargs) as client:
            response = client.post(
                f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Qwen 教学计划响应缺少正文") from exc
        return self._parse(content, source)

    def _prompt(self, source: TeachingPlanSource) -> str:
        timeline = self._pose_timeline(source)
        return (
            f"请把《{source.action_name}》这段 {source.pose.duration_seconds:.1f} 秒参考动作"
            "拆成 2-8 个连续教学阶段。阶段时间必须从 0 秒开始，且不能超出片段时长。\n"
            "每段输出 start_time、end_time、title、description、mnemonic、pitfall、"
            "priority（优先/建议/了解）、suggested_focus（auto/hands/arms/torso/lower/timing）、"
            "metric（timing/trajectory/angle）和 body_part。\n"
            "另外输出 overall_summary、warm_up_tips、practice_plan、image_generation_prompt。"
            "图片提示词只作为文本保存，本系统不会自动生成图片。不要输出 Markdown。\n"
            "JSON 结构："
            '{"overall_summary":"...","segments":[{"start_time":0,"end_time":1,'
            '"title":"...","description":"...","mnemonic":"...","pitfall":"...",'
            '"priority":"优先","suggested_focus":"arms","metric":"trajectory",'
            '"body_part":"双臂"}],"warm_up_tips":["..."],"practice_plan":"...",'
            '"image_generation_prompt":"..."}\n'
            f"MediaPipe 归一化时间线：{json.dumps(timeline, ensure_ascii=False)}"
        )

    def _pose_timeline(self, source: TeachingPlanSource) -> list[dict[str, Any]]:
        normalized = normalize_pose(source.pose)
        count = min(max(2, self.settings.qwen_max_frames), len(normalized.coords))
        indices = np.linspace(0, len(normalized.coords) - 1, count, dtype=int)
        joint_names = {
            11: "左肩",
            12: "右肩",
            15: "左手腕",
            16: "右手腕",
            23: "左髋",
            24: "右髋",
            27: "左踝",
            28: "右踝",
        }
        timeline: list[dict[str, Any]] = []
        for index in indices:
            joints = {
                name: [round(float(value), 3) for value in normalized.coords[index, joint, :2]]
                for joint, name in joint_names.items()
            }
            timeline.append(
                {
                    "time_seconds": round(float(source.pose.frame_times[index]), 2),
                    "joints": joints,
                }
            )
        return timeline

    def _reference_frame_urls(self, path: Path) -> list[str]:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return []
        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            picks = min(self.settings.qwen_max_frames, frame_count)
            indices = (
                np.linspace(0, max(frame_count - 1, 0), picks, dtype=int) if picks else []
            )
            urls: list[str] = []
            for index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
                ok, frame = cap.read()
                if not ok:
                    continue
                height, width = frame.shape[:2]
                if width > 480:
                    frame = cv2.resize(frame, (480, round(height * 480 / width)))
                encoded, buffer = cv2.imencode(
                    ".jpg",
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 82],
                )
                if encoded:
                    payload = base64.b64encode(buffer.tobytes()).decode("ascii")
                    urls.append(f"data:image/jpeg;base64,{payload}")
            return urls
        finally:
            cap.release()

    def _parse(self, content: str, source: TeachingPlanSource) -> TeachingPlan:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```")
            cleaned = cleaned.removesuffix("```").strip()
        payload = json.loads(cleaned)
        raw_segments = payload.get("segments") or payload.get("steps")
        if not isinstance(raw_segments, list) or not raw_segments:
            raise ValueError("Qwen 教学计划没有有效阶段")
        duration = source.source_end_seconds - source.source_start_seconds
        segments: list[TeachingSegment] = []
        for index, item in enumerate(raw_segments):
            if not isinstance(item, dict):
                raise ValueError("Qwen 教学阶段格式无效")
            fallback_start = duration * index / len(raw_segments)
            fallback_end = duration * (index + 1) / len(raw_segments)
            local_start = float(item.get("start_time", fallback_start))
            local_end = float(item.get("end_time", fallback_end))
            metric = str(item.get("metric", "trajectory"))
            if metric not in {"timing", "trajectory", "angle"}:
                metric = "trajectory"
            focus = str(item.get("suggested_focus", source.default_focus))
            if focus not in {"auto", "hands", "arms", "torso", "lower", "timing", "upper"}:
                focus = source.default_focus
            priority = str(item.get("priority", "建议"))
            if priority not in {"优先", "建议", "了解"}:
                priority = "建议"
            body_part = str(item.get("body_part") or self._default_body_part(focus))
            segments.append(
                TeachingSegment(
                    start_seconds=source.source_start_seconds + local_start,
                    end_seconds=source.source_start_seconds + local_end,
                    title=str(item.get("title") or f"第 {index + 1} 段"),
                    description=str(item.get("description") or "观察动作的启动与落位。"),
                    mnemonic=str(item.get("mnemonic") or ""),
                    pitfall=str(item.get("pitfall") or ""),
                    priority=priority,  # type: ignore[arg-type]
                    suggested_focus=focus,  # type: ignore[arg-type]
                    metric=metric,  # type: ignore[arg-type]
                    body_part=body_part,
                )
            )
        return TeachingPlan(
            action_id=source.action_id,
            source_hash=source.source_hash,
            source_start_seconds=source.source_start_seconds,
            source_end_seconds=source.source_end_seconds,
            overall_summary=str(payload.get("overall_summary") or ""),
            segments=segments,
            warmups=[str(item) for item in payload.get("warm_up_tips", [])][:3],
            practice_plan=str(payload.get("practice_plan") or ""),
            image_prompt=str(payload.get("image_generation_prompt") or ""),
            provenance=TeachingPlanProvenance(
                generator="qwen_reference_teaching",
                model=self.settings.qwen_model,
            ),
        )

    @staticmethod
    def _default_body_part(focus: str) -> str:
        return {
            "hands": "双手",
            "arms": "双臂",
            "torso": "躯干",
            "upper": "上半身",
            "lower": "双腿",
            "timing": "全身",
            "auto": "躯干",
        }[focus]


class TeachingPlanStore:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def path(self, action_id: str) -> Path:
        if not ACTION_ID.fullmatch(action_id):
            raise ValueError("教学计划动作 ID 无效")
        return self.directory / f"{action_id}.json"

    def load(self, action_id: str) -> TeachingPlan | None:
        path = self.path(action_id)
        if not path.is_file():
            return None
        try:
            return TeachingPlan.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def save(self, plan: TeachingPlan) -> None:
        target = self.path(plan.action_id)
        pending = target.with_name(f".{target.name}-{uuid4().hex}.pending")
        try:
            pending.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            pending.replace(target)
        finally:
            pending.unlink(missing_ok=True)


class TeachingPlanService:
    def __init__(self, store: TeachingPlanStore, generator: TeachingPlanGenerator):
        self.store = store
        self.generator = generator
        self._state_lock = threading.Lock()
        self._action_locks: dict[str, threading.Lock] = {}
        self._latest_hashes: dict[str, str] = {}

    def prepare(self, source: TeachingPlanSource) -> TeachingPlan | None:
        with self._state_lock:
            self._latest_hashes[source.action_id] = source.source_hash
            action_lock = self._action_locks.setdefault(source.action_id, threading.Lock())
        with action_lock:
            with self._state_lock:
                if self._latest_hashes.get(source.action_id) != source.source_hash:
                    return None
            current = self.store.load(source.action_id)
            if current and current.source_hash == source.source_hash:
                return current
            if not self.generator.configured:
                return None
            try:
                plan = self.generator.generate(source)
                self._validate_plan(plan, source)
                with self._state_lock:
                    if self._latest_hashes.get(source.action_id) != source.source_hash:
                        return None
                self.store.save(plan)
                return plan
            except Exception:
                logger.warning(
                    "Teaching plan generation failed for %s",
                    source.action_id,
                    exc_info=True,
                )
                return None

    @staticmethod
    def _validate_plan(plan: TeachingPlan, source: TeachingPlanSource) -> None:
        if plan.action_id != source.action_id or plan.source_hash != source.source_hash:
            raise ValueError("教学计划与参考素材不匹配")
        if (
            plan.source_start_seconds != source.source_start_seconds
            or plan.source_end_seconds != source.source_end_seconds
        ):
            raise ValueError("教学计划时间范围与参考素材不匹配")

    def segment_for(
        self,
        action_id: str,
        timestamp_seconds: float,
        *,
        expected_source_hash: str | None = None,
    ) -> TeachingSegment | None:
        plan = self.store.load(action_id)
        if not plan:
            return None
        if expected_source_hash is None or plan.source_hash != expected_source_hash:
            return None
        for index, segment in enumerate(plan.segments):
            is_last = index == len(plan.segments) - 1
            if segment.start_seconds <= timestamp_seconds and (
                timestamp_seconds < segment.end_seconds
                or (is_last and timestamp_seconds <= segment.end_seconds)
            ):
                return segment
        return None
