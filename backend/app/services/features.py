from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .pose import PoseSequence


LANDMARK_NAMES = {
    0: "鼻子", 11: "左肩", 12: "右肩", 13: "左肘", 14: "右肘",
    15: "左手腕", 16: "右手腕", 23: "左髋", 24: "右髋",
    25: "左膝", 26: "右膝", 27: "左踝", 28: "右踝",
}

BODY_GROUPS = {
    "左手势": [15, 17, 19, 21],
    "右手势": [16, 18, 20, 22],
    "左臂": [11, 13, 15],
    "右臂": [12, 14, 16],
    "左腿": [23, 25, 27],
    "右腿": [24, 26, 28],
    "躯干": [11, 12, 23, 24],
}

ANGLE_TRIPLETS = {
    "左手势": (17, 15, 21),
    "右手势": (18, 16, 22),
    "左肘": (11, 13, 15),
    "右肘": (12, 14, 16),
    "左肩": (13, 11, 23),
    "右肩": (14, 12, 24),
    "左膝": (23, 25, 27),
    "右膝": (24, 26, 28),
    "左髋": (11, 23, 25),
    "右髋": (12, 24, 26),
}


@dataclass(slots=True)
class NormalizedPose:
    coords: np.ndarray  # [T, 33, 3]
    visibility: np.ndarray  # [T, 33]
    frame_times: np.ndarray
    duration_seconds: float


def normalize_pose(sequence: PoseSequence) -> NormalizedPose:
    coords = sequence.landmarks[:, :, :3].astype(np.float32).copy()
    visibility = sequence.landmarks[:, :, 3].astype(np.float32).copy()
    for index in range(coords.shape[0]):
        frame = coords[index]
        hip_center = (frame[23] + frame[24]) / 2.0
        shoulder_center = (frame[11] + frame[12]) / 2.0
        shoulder_vector = frame[12, :2] - frame[11, :2]
        shoulder_width = float(np.linalg.norm(shoulder_vector))
        torso_length = float(np.linalg.norm(shoulder_center[:2] - hip_center[:2]))
        scale = max(shoulder_width, torso_length, 1e-4)
        frame -= hip_center
        angle = math.atan2(float(shoulder_vector[1]), float(shoulder_vector[0]))
        cos_a, sin_a = math.cos(-angle), math.sin(-angle)
        rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float32)
        frame[:, :2] = frame[:, :2] @ rotation.T
        frame /= scale
        coords[index] = frame
    return NormalizedPose(
        coords=coords,
        visibility=visibility,
        frame_times=sequence.frame_times,
        duration_seconds=sequence.duration_seconds,
    )


def pose_feature_matrix(pose: NormalizedPose, joints: list[int] | None = None) -> np.ndarray:
    joints = joints or [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
    return pose.coords[:, joints, :2].reshape(pose.coords.shape[0], -1)


def joint_angle(coords: np.ndarray, triplet: tuple[int, int, int]) -> np.ndarray:
    a, b, c = triplet
    ba = coords[:, a, :2] - coords[:, b, :2]
    bc = coords[:, c, :2] - coords[:, b, :2]
    numerator = np.sum(ba * bc, axis=1)
    denominator = np.linalg.norm(ba, axis=1) * np.linalg.norm(bc, axis=1)
    cosine = np.clip(numerator / np.maximum(denominator, 1e-6), -1.0, 1.0)
    return np.degrees(np.arccos(cosine))


def motion_signal(pose: NormalizedPose, joints: list[int]) -> np.ndarray:
    coords = pose.coords[:, joints, :2]
    velocity = np.diff(coords, axis=0, prepend=coords[:1])
    return np.linalg.norm(velocity, axis=2).mean(axis=1)


def phase_name(frame_index: int, frame_count: int) -> str:
    if frame_count <= 1:
        return "动作中段"
    ratio = frame_index / (frame_count - 1)
    if ratio < 0.25:
        return "起势"
    if ratio < 0.5:
        return "第一段衔接"
    if ratio < 0.75:
        return "第二段衔接"
    return "收势"
