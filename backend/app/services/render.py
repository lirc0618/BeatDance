from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .pose import PoseSequence
from .video import read_frame_at


CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (25, 27),
    (24, 26), (26, 28),
]
GROUP_TO_JOINTS = {
    "左臂": [11, 13, 15], "右臂": [12, 14, 16],
    "左腿": [23, 25, 27], "右腿": [24, 26, 28],
    "躯干": [11, 12, 23, 24],
    "左肘": [11, 13, 15], "右肘": [12, 14, 16],
    "左肩": [13, 11, 23], "右肩": [14, 12, 24],
    "左膝": [23, 25, 27], "右膝": [24, 26, 28],
    "左髋": [11, 23, 25], "右髋": [12, 24, 26],
}


def _fit(frame: np.ndarray, width: int = 540, height: int = 720) -> np.ndarray:
    canvas = np.full((height, width, 3), 245, dtype=np.uint8)
    scale = min(width / frame.shape[1], height / frame.shape[0])
    resized = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)))
    x = (width - resized.shape[1]) // 2
    y = (height - resized.shape[0]) // 2
    canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return canvas


def _draw_pose(frame: np.ndarray, landmarks: np.ndarray, highlight: str) -> None:
    h, w = frame.shape[:2]
    points = [(int(item[0] * w), int(item[1] * h)) for item in landmarks]
    highlighted = set(GROUP_TO_JOINTS.get(highlight, []))
    for a, b in CONNECTIONS:
        color = (50, 50, 255) if a in highlighted or b in highlighted else (0, 215, 255)
        cv2.line(frame, points[a], points[b], color, 3, cv2.LINE_AA)
    for index in {joint for pair in CONNECTIONS for joint in pair}:
        color = (40, 40, 255) if index in highlighted else (255, 255, 255)
        cv2.circle(frame, points[index], 5, color, -1, cv2.LINE_AA)


def create_comparison_image(
    reference_video: Path,
    candidate_video: Path,
    reference_pose: PoseSequence,
    candidate_pose: PoseSequence,
    reference_frame_index: int,
    candidate_frame_index: int,
    highlight: str,
    output_path: Path,
    mirror_candidate_frame: bool = False,
) -> Path | None:
    ref_time = float(reference_pose.frame_times[min(reference_frame_index, len(reference_pose.frame_times) - 1)])
    cand_time = float(candidate_pose.frame_times[min(candidate_frame_index, len(candidate_pose.frame_times) - 1)])
    ref_frame = read_frame_at(reference_video, ref_time)
    cand_frame = read_frame_at(candidate_video, cand_time)
    if cand_frame is not None and mirror_candidate_frame:
        cand_frame = cv2.flip(cand_frame, 1)
    if ref_frame is None or cand_frame is None:
        return None
    _draw_pose(ref_frame, reference_pose.landmarks[reference_frame_index], highlight)
    _draw_pose(cand_frame, candidate_pose.landmarks[candidate_frame_index], highlight)
    ref_frame = _fit(ref_frame)
    cand_frame = _fit(cand_frame)
    cv2.putText(ref_frame, "REFERENCE", (18, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(cand_frame, "YOUR TRY", (18, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    combined = np.concatenate([ref_frame, cand_frame], axis=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), combined, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return output_path
