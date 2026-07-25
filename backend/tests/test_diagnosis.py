from pathlib import Path

import numpy as np

from app.services.diagnosis import ActionRegistry, compare_poses
from app.services.features import NormalizedPose


def _skeleton(frame_count: int = 60) -> np.ndarray:
    coords = np.zeros((frame_count, 33, 3), dtype=np.float32)
    fixed = {
        11: (-0.4, -1.0), 12: (0.4, -1.0),
        13: (-0.7, -0.3), 14: (0.7, -0.3),
        15: (-0.9, 0.4), 16: (0.9, 0.4),
        23: (-0.25, 0.0), 24: (0.25, 0.0),
        25: (-0.25, 0.8), 26: (0.25, 0.8),
        27: (-0.25, 1.6), 28: (0.25, 1.6),
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


def test_card_point_search_returns_diverse_views():
    registry = ActionRegistry(Path(__file__).parents[1] / "app" / "data" / "actions.json")
    results = registry.search_tutorials("arm_wave", "timing", "右臂", focus="upper", limit=3)

    assert len(results) == 3
    assert len({item.view_type for item in results}) == 3
    assert results[0].error_type == "timing"
    assert results[0].why_matched


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
