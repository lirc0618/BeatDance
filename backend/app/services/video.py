from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import cv2
from fastapi import UploadFile


@dataclass(slots=True)
class VideoMetadata:
    duration_seconds: float
    fps: float
    frame_count: int
    width: int
    height: int


class VideoValidationError(ValueError):
    pass


def probe_video(path: Path) -> VideoMetadata:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoValidationError("无法读取视频，请上传 MP4/MOV 等常见格式")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if fps <= 0 or frame_count <= 0:
        raise VideoValidationError("视频缺少有效帧率或帧信息")
    return VideoMetadata(
        duration_seconds=frame_count / fps,
        fps=fps,
        frame_count=frame_count,
        width=width,
        height=height,
    )


async def save_upload(upload: UploadFile, directory: Path, max_upload_mb: int) -> Path:
    suffix = Path(upload.filename or "video.mp4").suffix.lower() or ".mp4"
    if suffix not in {".mp4", ".mov", ".m4v", ".avi", ".webm"}:
        raise VideoValidationError("仅支持 MP4、MOV、M4V、AVI 或 WEBM 视频")
    path = directory / f"{uuid4().hex}{suffix}"
    size = 0
    with path.open("wb") as target:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_upload_mb * 1024 * 1024:
                target.close()
                path.unlink(missing_ok=True)
                raise VideoValidationError(f"视频不能超过 {max_upload_mb}MB")
            target.write(chunk)
    return path


def normalize_video(input_path: Path, output_path: Path) -> Path:
    """转为 H.264/yuv420p，便于 OpenCV、小程序和浏览器统一读取。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return input_path
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-an",
        "-vf",
        "scale='min(720,iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if completed.returncode != 0:
        return input_path
    return output_path


def validate_duration(metadata: VideoMetadata, minimum: float, maximum: float) -> None:
    if metadata.duration_seconds < minimum or metadata.duration_seconds > maximum:
        raise VideoValidationError(
            f"视频时长需在 {minimum:g}–{maximum:g} 秒之间，当前约 {metadata.duration_seconds:.1f} 秒"
        )


def read_frame_at(path: Path, time_seconds: float):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, time_seconds) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None
