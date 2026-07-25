import numpy as np

from app.services.dtw import dynamic_time_warping


def test_dtw_handles_different_speeds():
    t1 = np.linspace(0, 2 * np.pi, 40)
    t2 = np.linspace(0, 2 * np.pi, 65)
    reference = np.column_stack([np.sin(t1), np.cos(t1)])
    candidate = np.column_stack([np.sin(t2), np.cos(t2)])
    result = dynamic_time_warping(reference, candidate)
    assert result.normalized_cost < 0.15
    assert result.path[0] == (0, 0)
    assert result.path[-1] == (39, 64)
