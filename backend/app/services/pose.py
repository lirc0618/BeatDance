from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

# MediaPipe Pose 33 点左右映射。
LEFT_RIGHT_PAIRS = [
    (1, 4), (2, 5), (3, 6), (7, 8), (9, 10),
    (11, 12), (13, 14), (15, 16), (17, 18), (19, 20),
    (21, 22), (23, 24), (25, 26), (27, 28), (29, 30),
    (31, 32),
]


@dataclass(slots=True)
class PoseSequence:
    landmarks: np.ndarray  # [T, 33, 4] x/y/z/visibility
    frame_times: np.ndarray
    source_fps: float
    duration_seconds: float
    coverage: float

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            landmarks=self.landmarks.astype(np.float32),
            frame_times=self.frame_times.astype(np.float32),
            source_fps=np.array([self.source_fps], dtype=np.float32),
            duration_seconds=np.array([self.duration_seconds], dtype=np.float32),
            coverage=np.array([self.coverage], dtype=np.float32),
        )

    @classmethod
    def load(cls, path: Path) -> PoseSequence:
        data = np.load(path)
        return cls(
            landmarks=data["landmarks"],
            frame_times=data["frame_times"],
            source_fps=float(data["source_fps"][0]),
            duration_seconds=float(data["duration_seconds"][0]),
            coverage=float(data["coverage"][0]),
        )


class PoseExtractionError(RuntimeError):
    pass


def _interpolate_missing(values: np.ndarray) -> np.ndarray:
    output = values.copy()
    t = np.arange(output.shape[0])
    for joint in range(output.shape[1]):
        for axis in range(3):
            series = output[:, joint, axis]
            valid = np.isfinite(series)
            if valid.sum() == 0:
                output[:, joint, axis] = 0.0
            elif valid.sum() == 1:
                output[:, joint, axis] = series[valid][0]
            else:
                output[:, joint, axis] = np.interp(t, t[valid], series[valid])
        visibility = output[:, joint, 3]
        visibility[~np.isfinite(visibility)] = 0.0
        output[:, joint, 3] = visibility
    return output


def _smooth(values: np.ndarray, window: int = 5) -> np.ndarray:
    if values.shape[0] < window:
        return values
    output = values.copy()
    kernel = np.ones(window, dtype=np.float32) / window
    left = window // 2
    right = window - 1 - left
    for joint in range(values.shape[1]):
        for axis in range(3):
            series = np.pad(values[:, joint, axis], (left, right), mode="edge")
            output[:, joint, axis] = np.convolve(series, kernel, mode="valid")
    return output


def extract_pose_sequence(
    video_path: Path,
    target_fps: float = 15.0,
    model_complexity: int = 1,
    min_detection_confidence: float = 0.5,
    min_tracking_confidence: float = 0.5,
) -> PoseSequence:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise PoseExtractionError("无法打开视频")

    source_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if source_fps <= 0 or frame_count <= 0:
        cap.release()
        raise PoseExtractionError("视频帧信息无效")

    sample_step = max(1, round(source_fps / target_fps))
    sampled: list[np.ndarray] = []
    times: list[float] = []
    detected_frames = 0
    frame_index = 0

    with mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=model_complexity,
        smooth_landmarks=True,
        enable_segmentation=False,
        min_detection_confidence=min_detection_confidence,
        min_tracking_confidence=min_tracking_confidence,
    ) as pose:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % sample_step != 0:
                frame_index += 1
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            current = np.full((33, 4), np.nan, dtype=np.float32)
            if result.pose_landmarks:
                detected_frames += 1
                for index, landmark in enumerate(result.pose_landmarks.landmark):
                    current[index] = [landmark.x, landmark.y, landmark.z, landmark.visibility]
            sampled.append(current)
            times.append(frame_index / source_fps)
            frame_index += 1

    cap.release()
    if not sampled:
        raise PoseExtractionError("视频中没有可分析帧")
    landmarks = np.stack(sampled)
    coverage = detected_frames / len(sampled)
    landmarks = _interpolate_missing(landmarks)
    landmarks = _smooth(landmarks)
    return PoseSequence(
        landmarks=landmarks,
        frame_times=np.asarray(times, dtype=np.float32),
        source_fps=source_fps,
        duration_seconds=frame_count / source_fps,
        coverage=coverage,
    )


def mirror_sequence(sequence: PoseSequence) -> PoseSequence:
    mirrored = sequence.landmarks.copy()
    mirrored[:, :, 0] = 1.0 - mirrored[:, :, 0]
    for left, right in LEFT_RIGHT_PAIRS:
        temp = mirrored[:, left, :].copy()
        mirrored[:, left, :] = mirrored[:, right, :]
        mirrored[:, right, :] = temp
    return PoseSequence(
        landmarks=mirrored,
        frame_times=sequence.frame_times.copy(),
        source_fps=sequence.source_fps,
        duration_seconds=sequence.duration_seconds,
        coverage=sequence.coverage,
    )
