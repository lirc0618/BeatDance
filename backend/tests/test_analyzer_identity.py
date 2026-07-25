import numpy as np

from app.services.analyzer import Analyzer
from app.services.features import NormalizedPose


def normalized_pose(offset: float) -> NormalizedPose:
    return NormalizedPose(
        coords=np.full((4, 33, 3), offset, dtype=np.float32),
        visibility=np.ones((4, 33), dtype=np.float32),
        frame_times=np.linspace(0, 1, 4, dtype=np.float32),
        duration_seconds=1.0,
    )


def test_pause_context_replaces_registered_reference_for_selected_action():
    pause_context = normalized_pose(1.0)
    registered = {
        "aini": normalized_pose(2.0),
        "jumpstyle": normalized_pose(3.0),
    }

    references = Analyzer.identity_references(
        expected_action_id="aini",
        pause_context=pause_context,
        registered_references=registered,
    )

    assert references["aini"] is pause_context
    assert references["jumpstyle"] is registered["jumpstyle"]
