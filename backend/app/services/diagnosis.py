from __future__ import annotations

import fcntl
import json
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import numpy as np

from ..schemas import Diagnosis, FocusKind, MetricDetail, Tutorial
from .dtw import DTWResult, aligned_pairs, dynamic_time_warping
from .features import (
    ANGLE_TRIPLETS,
    BODY_GROUPS,
    NormalizedPose,
    joint_angle,
    motion_signal,
    phase_name,
    pose_feature_matrix,
)

UPPER_WORDS = ("臂", "肘", "肩", "腕", "手", "躯干")
LOWER_WORDS = ("腿", "膝", "髋", "脚", "踝")


@dataclass(slots=True)
class ComparisonBundle:
    diagnosis: Diagnosis
    dtw: DTWResult
    key_reference_frame: int
    key_candidate_frame: int
    mirrored: bool


def _part_focus(body_part: str) -> str:
    if any(word in body_part for word in UPPER_WORDS):
        return "upper"
    if any(word in body_part for word in LOWER_WORDS):
        return "lower"
    return "auto"


def _focus_aware_max(values: dict[str, float], focus: FocusKind, absolute: bool = False) -> str:
    score = (lambda key: abs(values[key])) if absolute else (lambda key: values[key])
    global_best = max(values, key=score)
    if focus not in ("upper", "lower"):
        return global_best
    candidates = [key for key in values if _part_focus(key) == focus]
    if not candidates:
        return global_best
    focused_best = max(candidates, key=score)
    # 用户圈选是意图提示，不允许压过明显更大的真实偏差。
    if score(focused_best) >= score(global_best) * 0.70:
        return focused_best
    return global_best


def _tutorial_result(action: dict[str, Any], item: dict[str, Any], reason: str) -> Tutorial:
    payload = dict(item)
    payload["why_matched"] = reason
    if not payload.get("url"):
        query = quote(f"{action['name']} {item['title']}", safe="")
        payload["url"] = f"https://www.douyin.com/search/{query}"
    return Tutorial(**payload)


class ActionRegistry:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.reload()

    def reload(self) -> None:
        lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        with self.lock, lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                version = self._file_version()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            actions = {item["id"]: item for item in data["actions"]}
            self.data = data
            self.actions = actions
            self.file_version = version

    def _file_version(self) -> tuple[int, int, int]:
        stat = self.path.stat()
        return stat.st_ino, stat.st_mtime_ns, stat.st_size

    def _reload_if_changed(self) -> None:
        if self._file_version() != self.file_version:
            self.reload()

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            self._reload_if_changed()
            return list(self.actions.values())

    def get(self, action_id: str) -> dict[str, Any]:
        with self.lock:
            self._reload_if_changed()
            if action_id not in self.actions:
                raise KeyError(f"未知动作：{action_id}")
            return self.actions[action_id]

    def replace_action(self, action: dict[str, Any]) -> bool:
        """Atomically append or replace one action and refresh live readers."""

        lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        with self.lock, lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            committed = False
            try:
                latest = json.loads(self.path.read_text(encoding="utf-8"))
                current = {item["id"]: item for item in latest["actions"]}
                created = action["id"] not in current
                items = [action if item["id"] == action["id"] else item for item in latest["actions"]]
                if created:
                    items.append(action)
                payload = {**latest, "actions": items}
                pending = self.path.with_name(f".{self.path.name}-{uuid4().hex}.pending")
                try:
                    pending.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    pending.replace(self.path)
                    committed = True
                finally:
                    try:
                        pending.unlink(missing_ok=True)
                    except OSError:
                        if not committed:
                            raise
                self.data = payload
                self.actions = {item["id"]: item for item in items}
                try:
                    self.file_version = self._file_version()
                except OSError:
                    # Force the next read to refresh; the catalog commit already
                    # succeeded and must never be reported as a failed publish.
                    self.file_version = (-1, -1, -1)
                return created
            finally:
                with suppress(OSError):
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def search_tutorials(
        self,
        action_id: str,
        metric: str,
        body_part: str,
        focus: FocusKind = "auto",
        limit: int = 3,
    ) -> list[Tutorial]:
        action = self.get(action_id)
        tutorials = action.get("tutorials", [])
        scored: list[tuple[float, dict[str, Any], str]] = []
        part_focus = _part_focus(body_part)
        for item in tutorials:
            score = 0.0
            reasons: list[str] = []
            if item.get("error_type") == metric:
                score += 5
                reasons.append("正好治这个问题")
            if item.get("body_part") == body_part:
                score += 3
                reasons.append(f"只盯{body_part}")
            elif _part_focus(str(item.get("body_part", ""))) == part_focus and part_focus != "auto":
                score += 1.5
                reasons.append("盯的是同一块")
            tags = set(item.get("tags", []))
            if focus != "auto" and focus in tags:
                score += 2
                reasons.append("就是你想看的部位")
            if focus == "timing" and item.get("error_type") == "timing":
                score += 2
                reasons.append("专治抢拍和慢拍")
            # 优先召回更适合短视频学习的局部/背面/慢速内容。
            if item.get("view_type") in {"局部特写", "背面跟练", "慢速分拍"}:
                score += 0.5
            scored.append((score, item, "、".join(reasons) or "换个角度更好懂"))

        scored.sort(key=lambda row: row[0], reverse=True)
        picked: list[Tutorial] = []
        used_views: set[str] = set()
        # 先保证拆解方式多样，再补齐数量。
        for _, item, reason in scored:
            view = str(item.get("view_type", "微练习"))
            if view in used_views:
                continue
            picked.append(_tutorial_result(action, item, reason))
            used_views.add(view)
            if len(picked) >= limit:
                return picked
        for _, item, reason in scored:
            if any(existing.id == item.get("id") for existing in picked):
                continue
            picked.append(_tutorial_result(action, item, reason))
            if len(picked) >= limit:
                break
        return picked

    def tutorial(self, action_id: str, metric: str, body_part: str) -> Tutorial | None:
        results = self.search_tutorials(action_id, metric, body_part, limit=1)
        return results[0] if results else None


def _cross_correlation_lag(reference: np.ndarray, candidate: np.ndarray, duration: float) -> float:
    length = max(len(reference), len(candidate), 2)
    x_old = np.linspace(0.0, 1.0, len(reference))
    y_old = np.linspace(0.0, 1.0, len(candidate))
    grid = np.linspace(0.0, 1.0, length)
    ref = np.interp(grid, x_old, reference)
    cand = np.interp(grid, y_old, candidate)
    ref = ref - ref.mean()
    cand = cand - cand.mean()
    if np.allclose(ref, 0) or np.allclose(cand, 0):
        return 0.0
    correlation = np.correlate(cand, ref, mode="full")
    lag_samples = int(np.argmax(correlation) - (length - 1))
    return lag_samples / max(length - 1, 1) * duration


def _search_query(action_name: str, metric: str, body_part: str, status: str) -> str:
    if status == "aligned":
        return f"{action_name} 原速 连贯 跟练 完整版"
    if metric == "timing":
        return f"{action_name} {body_part} 拍点 慢速分拍 背面跟练"
    if metric == "trajectory":
        return f"{action_name} {body_part} 运动路线 局部特写 慢动作"
    return f"{action_name} {body_part} 幅度 关键帧 定格拆解"


def compare_poses(
    action_id: str,
    reference: NormalizedPose,
    candidate: NormalizedPose,
    registry: ActionRegistry,
    mirrored: bool,
    focus: FocusKind = "auto",
) -> ComparisonBundle:
    action = registry.get(action_id)
    config = action.get("diagnosis", {})
    thresholds = config.get("thresholds", {})
    weights = config.get("weights", {})
    timing_limit = float(thresholds.get("timing_seconds", 0.55))
    trajectory_limit = float(thresholds.get("trajectory", 0.55))
    angle_limit = float(thresholds.get("angle_degrees", 55.0))
    aligned_threshold = float(config.get("aligned_threshold", 0.22))

    dtw = dynamic_time_warping(pose_feature_matrix(reference), pose_feature_matrix(candidate))
    ref_indices, cand_indices = aligned_pairs(dtw.path)

    trajectory_by_group: dict[str, float] = {}
    trajectory_peak: dict[str, tuple[int, int]] = {}
    for group_name, joints in BODY_GROUPS.items():
        diff = reference.coords[ref_indices][:, joints, :2] - candidate.coords[cand_indices][:, joints, :2]
        per_pair = np.linalg.norm(diff, axis=2).mean(axis=1)
        trajectory_by_group[group_name] = float(per_pair.mean())
        peak = int(np.argmax(per_pair))
        trajectory_peak[group_name] = (int(ref_indices[peak]), int(cand_indices[peak]))

    trajectory_group = _focus_aware_max(trajectory_by_group, focus)
    trajectory_error = trajectory_by_group[trajectory_group]

    angle_by_joint: dict[str, float] = {}
    angle_peak: dict[str, tuple[int, int]] = {}
    for joint_name, triplet in ANGLE_TRIPLETS.items():
        ref_angles = joint_angle(reference.coords, triplet)[ref_indices]
        cand_angles = joint_angle(candidate.coords, triplet)[cand_indices]
        differences = np.abs(ref_angles - cand_angles)
        angle_by_joint[joint_name] = float(np.mean(differences))
        peak = int(np.argmax(differences))
        angle_peak[joint_name] = (int(ref_indices[peak]), int(cand_indices[peak]))
    angle_joint = _focus_aware_max(angle_by_joint, focus)
    angle_error = angle_by_joint[angle_joint]

    timing_by_group: dict[str, float] = {}
    for group_name, joints in BODY_GROUPS.items():
        timing_by_group[group_name] = _cross_correlation_lag(
            motion_signal(reference, joints),
            motion_signal(candidate, joints),
            min(reference.duration_seconds, candidate.duration_seconds),
        )
    timing_group = _focus_aware_max(timing_by_group, focus, absolute=True)
    timing_offset = timing_by_group[timing_group]

    timing_norm = min(abs(timing_offset) / max(timing_limit, 1e-6), 1.0)
    trajectory_norm = min(trajectory_error / max(trajectory_limit, 1e-6), 1.0)
    angle_norm = min(angle_error / max(angle_limit, 1e-6), 1.0)
    weighted = {
        "timing": timing_norm * float(weights.get("timing", 1.05)),
        "trajectory": trajectory_norm * float(weights.get("trajectory", 1.0)),
        "angle": angle_norm * float(weights.get("angle", 0.95)),
    }
    if focus == "timing":
        weighted["timing"] *= 1.20
    primary_metric = max(weighted, key=weighted.get)
    issue_strength = float(max(weighted.values()))

    if primary_metric == "timing":
        body_part = timing_group
        if timing_offset < 0:
            primary_error = f"{body_part}抢跑了，像偷偷开了倍速"
            feedback = f"先别管全身。让{body_part}晚一点出发，嘴里数到“走”再动。"
        else:
            primary_error = f"{body_part}慢半拍，像网卡了一下"
            feedback = f"先别管全身。给{body_part}一点提前量，嘴里喊“走”时它就出发。"
        drill = f"开启“{body_part}单机模式”：跟四拍做 3 遍，再把全身叫回来。"
        ref_key, cand_key = trajectory_peak.get(
            body_part, (len(reference.coords) // 2, len(candidate.coords) // 2)
        )
    elif primary_metric == "trajectory":
        body_part = trajectory_group
        primary_error = f"{body_part}的导航走偏了"
        feedback = f"先把注意力放在{body_part}：它这次绕了点路。只看“从哪出发、最后停哪”。"
        drill = f"开 0.5 倍速，把{body_part}当成鼠标光标，沿同一条路走 3 遍。"
        ref_key, cand_key = trajectory_peak[trajectory_group]
    else:
        body_part = angle_joint
        primary_error = f"{body_part}这张“定格照”还没摆到位"
        feedback = f"先把注意力放在{body_part}。把这个造型摆得更像，再追求连贯。"
        drill = f"停在最大动作那一帧 2 秒，照着摆{body_part}，摆对再连起来。"
        ref_key, cand_key = angle_peak[angle_joint]

    status = "issue_detected"
    if issue_strength < aligned_threshold:
        status = "aligned"
        primary_error = "这把对味了，动作已经像了"
        feedback = "别再抠零件啦。现在最重要的是一口气做完，别把顺手的动作想复杂。"
        drill = "按原速完整来 2 遍：不停、不回看，让身体自己记住。"

    phase = phase_name(ref_key, len(reference.coords))
    confidence = float(np.clip(0.58 + abs(issue_strength - aligned_threshold) * 0.45, 0.58, 0.96))
    search_results = registry.search_tutorials(action_id, primary_metric, body_part, focus=focus, limit=3)
    tutorial = search_results[0] if search_results and status != "aligned" else None
    if status == "aligned":
        search_results = registry.search_tutorials(action_id, "timing", body_part, focus="auto", limit=3)

    metrics = [
        MetricDetail(
            kind="timing",
            score=abs(timing_offset),
            normalized_score=timing_norm,
            body_part=timing_group,
            phase=phase,
            human_value=(
                "基本同步"
                if abs(timing_offset) < 0.05
                else f"快了 {abs(timing_offset):.1f} 秒"
                if timing_offset < 0
                else f"慢了 {abs(timing_offset):.1f} 秒"
            ),
        ),
        MetricDetail(
            kind="trajectory",
            score=trajectory_error,
            normalized_score=trajectory_norm,
            body_part=trajectory_group,
            phase=phase,
            human_value=(
                "路线很稳"
                if trajectory_norm < 0.08
                else "稍微走偏"
                if trajectory_norm < 0.45
                else "绕了点路"
                if trajectory_norm < 0.8
                else "明显走偏"
            ),
        ),
        MetricDetail(
            kind="angle",
            score=angle_error,
            normalized_score=angle_norm,
            body_part=angle_joint,
            phase=phase,
            human_value=(
                "造型到位"
                if angle_norm < 0.08
                else "造型差一点"
                if angle_norm < 0.45
                else "还得再打开"
                if angle_norm < 0.8
                else "造型没摆开"
            ),
        ),
    ]

    diagnosis = Diagnosis(
        action_id=action_id,
        status=status,  # type: ignore[arg-type]
        phase=phase,
        primary_metric=primary_metric,  # type: ignore[arg-type]
        primary_error=primary_error,
        body_part=body_part,
        priority_feedback=feedback,
        drill=drill,
        confidence=confidence,
        timing_offset_seconds=float(timing_offset),
        trajectory_error=float(trajectory_error),
        angle_error_degrees=float(angle_error),
        metrics=metrics,
        user_focus=focus,
        search_query=_search_query(action["name"], primary_metric, body_part, status),
        search_results=search_results,
        tutorial=tutorial,
    )
    return ComparisonBundle(
        diagnosis=diagnosis,
        dtw=dtw,
        key_reference_frame=ref_key,
        key_candidate_frame=cand_key,
        mirrored=mirrored,
    )


def calculate_improvement(baseline: Diagnosis, current: Diagnosis) -> tuple[bool, float]:
    """Compare the second attempt against the first attempt's primary card point."""

    target_metric = baseline.primary_metric
    # Normalized scores are capped at 1.0 for diagnosis display. Comparing the
    # uncapped measurement preserves visible progress when both attempts exceed
    # the diagnosis threshold.
    baseline_score = next(metric.score for metric in baseline.metrics if metric.kind == target_metric)
    current_score = next(metric.score for metric in current.metrics if metric.kind == target_metric)
    percentage = (baseline_score - current_score) / max(baseline_score, 1e-6) * 100.0
    improved = current.status == "aligned" or percentage > 5.0
    return improved, percentage
