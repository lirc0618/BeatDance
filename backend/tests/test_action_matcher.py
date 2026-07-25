import numpy as np

from app.services.action_matcher import assess_action_match
from app.services.features import NormalizedPose


def pose(offset: float) -> NormalizedPose:
    coords = np.zeros((6, 33, 3), dtype=np.float32)
    coords[:, 11:29, 0] = offset
    coords[:, 11:29, 1] = np.linspace(0, 1, 6, dtype=np.float32)[:, None]
    return NormalizedPose(
        coords=coords,
        visibility=np.ones((6, 33), dtype=np.float32),
        frame_times=np.linspace(0, 1, 6, dtype=np.float32),
        duration_seconds=1.0,
    )


def test_uploaded_motion_matching_another_dance_is_rejected():
    references = {
        "aini": pose(0.0),
        "jumpstyle": pose(2.0),
    }

    result = assess_action_match(
        expected_action_id="aini",
        candidate_variants=[pose(2.0)],
        references=references,
        action_names={"aini": "爱你", "jumpstyle": "Jumpstyle"},
    )

    assert result.matched is False
    assert result.closest_action_id == "jumpstyle"
    assert result.message == "这段更像《Jumpstyle》，不是当前的《爱你》。请换成同一段动作再试。"


def test_unknown_motion_is_rejected_without_guessing_a_dance_name():
    result = assess_action_match(
        expected_action_id="aini",
        candidate_variants=[pose(5.0)],
        references={"aini": pose(0.0), "jumpstyle": pose(2.0)},
        action_names={"aini": "爱你", "jumpstyle": "Jumpstyle"},
    )

    assert result.matched is False
    assert result.closest_action_id is None
    assert result.message == "这段动作和《爱你》对不上。请上传同一段舞的 3–8 秒模仿。"


def test_selected_dance_passes_the_identity_gate():
    result = assess_action_match(
        expected_action_id="aini",
        candidate_variants=[pose(0.05)],
        references={"aini": pose(0.0), "jumpstyle": pose(2.0)},
        action_names={"aini": "爱你", "jumpstyle": "Jumpstyle"},
    )

    assert result.matched is True
    assert result.closest_action_id == "aini"
    assert result.message == "动作身份通过：这段和《爱你》属于同一套动作。"
