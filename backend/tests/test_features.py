import numpy as np

from app.services.features import joint_angle


def test_joint_angle_right_angle():
    coords = np.zeros((1, 33, 3), dtype=np.float32)
    coords[0, 11, :2] = [0, 1]
    coords[0, 13, :2] = [0, 0]
    coords[0, 15, :2] = [1, 0]
    angle = joint_angle(coords, (11, 13, 15))[0]
    assert abs(angle - 90) < 1e-4
