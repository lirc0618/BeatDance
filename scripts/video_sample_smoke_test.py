#!/usr/bin/env python3
"""Smoke-test the real bundled dance sample without requiring MediaPipe.

Validates the parts of the upload pipeline that can be tested independently:
- actual H.264 decoding
- 3–8 second duration gate
- frame seeking
- normalization/transcoding

The full pose extraction path still requires the Python 3.11 Docker runtime with
MediaPipe installed.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from app.services.video import normalize_video, probe_video, read_frame_at, validate_duration


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--video",
        type=Path,
        default=Path("assets/samples/open_sources/breakdance_6_step.mp4"),
    )
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"sample missing: {args.video}")

    metadata = probe_video(args.video)
    validate_duration(metadata, 3.0, 8.0)
    middle_frame = read_frame_at(args.video, metadata.duration_seconds / 2)
    if middle_frame is None:
        raise SystemExit("failed to seek and decode middle frame")

    with tempfile.TemporaryDirectory() as temp_dir:
        normalized = Path(temp_dir) / "normalized.mp4"
        result_path = normalize_video(args.video, normalized)
        normalized_metadata = probe_video(result_path)

    report = {
        "status": "passed",
        "source": str(args.video),
        "metadata": asdict(metadata),
        "middle_frame_shape": list(middle_frame.shape),
        "normalized_metadata": asdict(normalized_metadata),
        "checks": {
            "h264_decode": True,
            "duration_3_to_8_seconds": True,
            "frame_seek": True,
            "ffmpeg_normalize": True,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
