from pathlib import Path

import numpy as np
import pytest

from app.schemas import Diagnosis, MetricDetail
from app.services.diagnosis import ActionRegistry, calculate_improvement, compare_poses
from app.services.features import NormalizedPose
from app.services.pause_coach import PauseCoach


def _skeleton(frame_count: int = 60) -> np.ndarray:
    coords = np.zeros((frame_count, 33, 3), dtype=np.float32)
    fixed = {
        11: (-0.4, -1.0),
        12: (0.4, -1.0),
        13: (-0.7, -0.3),
        14: (0.7, -0.3),
        15: (-0.9, 0.4),
        16: (0.9, 0.4),
        23: (-0.25, 0.0),
        24: (0.25, 0.0),
        25: (-0.25, 0.8),
        26: (0.25, 0.8),
        27: (-0.25, 1.6),
        28: (0.25, 1.6),
    }
    for joint, (x, y) in fixed.items():
        coords[:, joint, 0] = x
        coords[:, joint, 1] = y
    return coords


def test_delayed_right_arm_is_timing_error():
    frame_count = 60
    reference_coords = _skeleton(frame_count)
    signal = np.sin(np.linspace(0, 2 * np.pi, frame_count))
    reference_coords[:, 16, 1] += 0.4 * signal

    candidate_coords = reference_coords.copy()
    candidate_coords[:, 16, 1] = np.r_[
        np.full(8, candidate_coords[0, 16, 1]),
        candidate_coords[:-8, 16, 1],
    ]
    times = np.linspace(0, 4, frame_count)
    reference = NormalizedPose(reference_coords, np.ones((frame_count, 33)), times, 4)
    candidate = NormalizedPose(candidate_coords, np.ones((frame_count, 33)), times, 4)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    result = compare_poses("arm_wave", reference, candidate, registry, mirrored=False)

    assert result.diagnosis.primary_metric == "timing"
    assert result.diagnosis.body_part == "右臂"
    assert result.diagnosis.timing_offset_seconds > 0.3
    assert "网卡" in result.diagnosis.primary_error
    assert "单机模式" in result.diagnosis.drill
    assert "动作延后" not in result.diagnosis.primary_error


def test_identical_motion_is_aligned():
    frame_count = 45
    coords = _skeleton(frame_count)
    signal = np.sin(np.linspace(0, 2 * np.pi, frame_count))
    coords[:, 16, 1] += 0.25 * signal
    times = np.linspace(0, 3, frame_count)
    reference = NormalizedPose(coords, np.ones((frame_count, 33)), times, 3)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    result = compare_poses("arm_wave", reference, reference, registry, mirrored=False)

    assert result.diagnosis.status == "aligned"
    assert result.diagnosis.tutorial is None
    assert "对味" in result.diagnosis.primary_error
    assert "别再抠" in result.diagnosis.priority_feedback
    timing = next(item for item in result.diagnosis.metrics if item.kind == "timing")
    trajectory = next(item for item in result.diagnosis.metrics if item.kind == "trajectory")
    angle = next(item for item in result.diagnosis.metrics if item.kind == "angle")
    assert timing.human_value == "基本同步"
    assert trajectory.human_value == "路线很稳"
    assert angle.human_value == "造型到位"


def test_shifted_arm_path_is_trajectory_error():
    frame_count = 60
    reference_coords = _skeleton(frame_count)
    signal = np.sin(np.linspace(0, 2 * np.pi, frame_count))
    reference_coords[:, 16, 1] += 0.4 * signal
    candidate_coords = reference_coords.copy()
    candidate_coords[:, [12, 14, 16], 0] += 0.35
    times = np.linspace(0, 4, frame_count)
    reference = NormalizedPose(reference_coords, np.ones((frame_count, 33)), times, 4)
    candidate = NormalizedPose(candidate_coords, np.ones((frame_count, 33)), times, 4)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    result = compare_poses("arm_wave", reference, candidate, registry, mirrored=False)

    assert result.diagnosis.status == "issue_detected"
    assert result.diagnosis.primary_metric == "trajectory"
    assert result.diagnosis.body_part == "右臂"
    assert "导航" in result.diagnosis.primary_error
    assert "参考轨迹" not in result.diagnosis.priority_feedback
    trajectory = next(item for item in result.diagnosis.metrics if item.kind == "trajectory")
    assert "偏差" not in trajectory.human_value


def test_bent_elbow_is_angle_error():
    frame_count = 60
    reference_coords = _skeleton(frame_count)
    signal = np.sin(np.linspace(0, 2 * np.pi, frame_count))
    reference_coords[:, 16, 1] += 0.4 * signal
    candidate_coords = reference_coords.copy()
    candidate_coords[:, 14, 1] += 0.8
    times = np.linspace(0, 4, frame_count)
    reference = NormalizedPose(reference_coords, np.ones((frame_count, 33)), times, 4)
    candidate = NormalizedPose(candidate_coords, np.ones((frame_count, 33)), times, 4)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    result = compare_poses("arm_wave", reference, candidate, registry, mirrored=False)

    assert result.diagnosis.status == "issue_detected"
    assert result.diagnosis.primary_metric == "angle"
    assert result.diagnosis.body_part == "右肘"
    assert "定格照" in result.diagnosis.primary_error
    angle = next(item for item in result.diagnosis.metrics if item.kind == "angle")
    assert "°" not in angle.human_value


def test_card_point_search_returns_diverse_views():
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")
    results = registry.search_tutorials("arm_wave", "timing", "右臂", focus="upper", limit=3)

    assert len(results) == 3
    assert len({item.view_type for item in results}) == 3
    assert results[0].error_type == "timing"
    assert "正好治" in results[0].why_matched
    assert all(item.url.startswith("https://www.douyin.com/search/") for item in results)


def test_timing_focus_is_preserved_in_result():
    frame_count = 60
    reference_coords = _skeleton(frame_count)
    signal = np.sin(np.linspace(0, 2 * np.pi, frame_count))
    reference_coords[:, 16, 1] += 0.4 * signal
    candidate_coords = reference_coords.copy()
    candidate_coords[:, 16, 1] = np.r_[
        np.full(7, candidate_coords[0, 16, 1]),
        candidate_coords[:-7, 16, 1],
    ]
    times = np.linspace(0, 4, frame_count)
    reference = NormalizedPose(reference_coords, np.ones((frame_count, 33)), times, 4)
    candidate = NormalizedPose(candidate_coords, np.ones((frame_count, 33)), times, 4)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    result = compare_poses("arm_wave", reference, candidate, registry, mirrored=False, focus="timing")

    assert result.diagnosis.user_focus == "timing"
    assert "慢速分拍" in result.diagnosis.search_query
    assert len(result.diagnosis.search_results) == 3


def test_improvement_tracks_the_original_primary_metric():
    def diagnosis(timing: float, trajectory: float, angle: float) -> Diagnosis:
        return Diagnosis(
            action_id="arm_wave",
            phase="起势",
            primary_metric="timing",
            primary_error="右臂动作延后",
            body_part="右臂",
            priority_feedback="先修拍点",
            drill="只练右臂",
            confidence=0.8,
            metrics=[
                MetricDetail(
                    kind="timing",
                    score=timing,
                    normalized_score=timing,
                    body_part="右臂",
                    phase="起势",
                    human_value="",
                ),
                MetricDetail(
                    kind="trajectory",
                    score=trajectory,
                    normalized_score=trajectory,
                    body_part="右臂",
                    phase="起势",
                    human_value="",
                ),
                MetricDetail(
                    kind="angle",
                    score=angle,
                    normalized_score=angle,
                    body_part="右肘",
                    phase="起势",
                    human_value="",
                ),
            ],
        )

    baseline = diagnosis(timing=0.8, trajectory=1.0, angle=1.0)
    current = diagnosis(timing=0.9, trajectory=0.0, angle=0.0)

    improved, percentage = calculate_improvement(baseline, current)

    assert improved is False
    assert percentage < 0


def test_improvement_uses_raw_score_when_normalized_values_are_saturated():
    def diagnosis(score: float) -> Diagnosis:
        return Diagnosis(
            action_id="groove_step",
            phase="起势",
            primary_metric="timing",
            primary_error="躯干动作延后",
            body_part="躯干",
            priority_feedback="先修拍点",
            drill="只练躯干",
            confidence=0.8,
            metrics=[
                MetricDetail(
                    kind="timing",
                    score=score,
                    normalized_score=1.0,
                    body_part="躯干",
                    phase="起势",
                    human_value="",
                ),
                MetricDetail(
                    kind="trajectory",
                    score=1.0,
                    normalized_score=1.0,
                    body_part="躯干",
                    phase="起势",
                    human_value="",
                ),
                MetricDetail(
                    kind="angle",
                    score=1.0,
                    normalized_score=1.0,
                    body_part="躯干",
                    phase="起势",
                    human_value="",
                ),
            ],
        )

    improved, percentage = calculate_improvement(
        diagnosis(score=1.4),
        diagnosis(score=0.7),
    )

    assert improved is True
    assert percentage == pytest.approx(50.0)


def test_pause_coach_explains_the_exact_moment_with_context_and_searches(tmp_path):
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")
    feed_dir = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    coach = PauseCoach(registry, feed_dir, tmp_path)

    insight = coach.explain("groove_step", timestamp_seconds=18.0)

    assert insight.timestamp_seconds == 18.0
    assert insight.feed_duration_seconds == 106.52
    assert insight.context_start_seconds == 16.5
    assert insight.context_end_seconds == 19.5
    assert insight.phase == "动作进入"
    assert "导航题" in insight.likely_stuck_at
    assert "手先撑稳还是脚先跨出" in insight.likely_stuck_at
    assert insight.watch_for.startswith("别一口气看全身")
    assert "检测到" not in insight.observed_motion
    assert insight.sampled_frame_count >= 20
    assert insight.suggested_focus == "lower"
    assert [item.view_type for item in insight.search_results] == [
        "背面跟练",
        "慢速分拍",
        "局部特写",
    ]


def test_pause_coach_rejects_a_timestamp_outside_the_feed(tmp_path):
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")
    feed_dir = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    coach = PauseCoach(registry, feed_dir, tmp_path)

    with pytest.raises(ValueError, match="暂停时间点必须位于视频时长范围内"):
        coach.explain("groove_step", timestamp_seconds=1000.0)
