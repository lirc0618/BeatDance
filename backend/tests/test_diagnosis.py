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
        17: (-1.0, 0.35),
        18: (1.0, 0.35),
        19: (-1.05, 0.4),
        20: (1.05, 0.4),
        21: (-0.98, 0.5),
        22: (0.98, 0.5),
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
    assert result.diagnosis.primary_error == "右臂掉拍了"
    assert result.diagnosis.overall_feedback == "整体能跟上动作，但关键部位还有明显偏差。"
    assert result.diagnosis.priority_feedback == "口令：喊“走”就动。"
    assert result.diagnosis.drill == "右臂单刷 ×3"


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
    assert result.diagnosis.primary_error == "这把同频了"
    assert result.diagnosis.overall_feedback == "整体节奏、路线和造型已经基本对上。"
    assert result.diagnosis.priority_feedback == "别抠，直接整套。"
    assert result.diagnosis.drill == "原速连跳 ×2"
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
    assert result.diagnosis.primary_error == "右臂跑线了"
    assert result.diagnosis.priority_feedback == "只认起点 → 落点。"
    assert result.diagnosis.drill == "0.5× 描线 ×3"
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
    assert result.diagnosis.primary_error == "右肘没卡住"
    assert result.diagnosis.priority_feedback == "先摆像，再连招。"
    assert result.diagnosis.drill == "定格 2 秒 ×3"
    angle = next(item for item in result.diagnosis.metrics if item.kind == "angle")
    assert "°" not in angle.human_value


def test_hand_focus_can_find_a_gesture_error_without_blaming_the_whole_arm():
    frame_count = 60
    reference_coords = _skeleton(frame_count)
    candidate_coords = reference_coords.copy()
    candidate_coords[:, [18, 20, 22], 0] += 0.45
    times = np.linspace(0, 4, frame_count)
    visibility = np.ones((frame_count, 33))
    reference = NormalizedPose(reference_coords, visibility, times, 4)
    candidate = NormalizedPose(candidate_coords, visibility, times, 4)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    result = compare_poses(
        "groove_step",
        reference,
        candidate,
        registry,
        mirrored=False,
        focus="hands",
    )

    assert result.diagnosis.status == "issue_detected"
    assert result.diagnosis.body_part == "右手势"
    assert result.diagnosis.user_focus == "hands"


def test_hand_focus_asks_for_a_clearer_clip_when_fingertips_are_not_visible():
    frame_count = 30
    coords = _skeleton(frame_count)
    times = np.linspace(0, 3, frame_count)
    visibility = np.ones((frame_count, 33))
    visibility[:, [15, 16, 17, 18, 19, 20, 21, 22]] = 0.1
    pose = NormalizedPose(coords, visibility, times, 3)
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")

    with pytest.raises(ValueError, match="手势看不清"):
        compare_poses(
            "groove_step",
            pose,
            pose,
            registry,
            mirrored=False,
            focus="hands",
        )


def test_card_point_search_returns_diverse_views():
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")
    results = registry.search_tutorials("arm_wave", "timing", "右臂", focus="upper", limit=3)

    assert len(results) == 3
    assert len({item.view_type for item in results}) == 3
    assert results[0].error_type == "timing"
    assert "正好治" in results[0].why_matched
    assert "、" not in results[0].why_matched
    assert all(item.url.startswith("/media/tutorials/") for item in results)
    assert all(item.local_asset.startswith("assets/tutorials/") for item in results)


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
    assert insight.feed_duration_seconds == 20.8
    assert insight.context_start_seconds == 16.5
    assert insight.context_end_seconds == 19.5
    assert insight.phase == "收尾定点"
    assert insight.likely_stuck_at.startswith("你锁定了收尾定点。按这个位置先排查：")
    assert "笑容可以松，拍子不能掉。" in insight.likely_stuck_at
    assert insight.watch_for == "口令：停住半拍。"
    assert "检测到" not in insight.observed_motion
    assert insight.sampled_frame_count >= 20
    assert insight.observed_motion.startswith("这秒")
    assert insight.suggested_focus == "arms"
    assert len(insight.search_results) == 3
    assert insight.search_results[0].error_type == "angle"


def test_pause_coach_rejects_a_timestamp_outside_the_feed(tmp_path):
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")
    feed_dir = Path(__file__).parents[2] / "assets" / "samples" / "open_sources"
    coach = PauseCoach(registry, feed_dir, tmp_path)

    with pytest.raises(ValueError, match="暂停时间点必须位于视频时长范围内"):
        coach.explain("groove_step", timestamp_seconds=1000.0)
