#!/usr/bin/env python3
"""Build the bundled diagnosis reference for the authorized Jazz Feed."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.pose import extract_pose_sequence  # noqa: E402

SOURCE = ROOT / "assets" / "samples" / "open_sources" / "爵士.MP4"
OUTPUT_DIR = ROOT / "assets" / "references"
ACTION_ID = "jazz_demo"


def main() -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("未找到 ffmpeg")
    if not SOURCE.is_file():
        raise SystemExit(f"缺少授权源视频：{SOURCE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generation = hashlib.sha256(
        SOURCE.read_bytes() + b"start=16.9;duration=5;fps=15;v1"
    ).hexdigest()[:12]
    video = OUTPUT_DIR / f"{ACTION_ID}-{generation}.mp4"
    sequence = OUTPUT_DIR / f"{ACTION_ID}-{generation}.npz"
    manifest = OUTPUT_DIR / f"{ACTION_ID}.current.json"
    nonce = uuid4().hex
    pending_video = OUTPUT_DIR / f".{ACTION_ID}-{nonce}.pending.mp4"
    pending_sequence = OUTPUT_DIR / f".{ACTION_ID}-{nonce}.pending.npz"
    pending_manifest = OUTPUT_DIR / f".{ACTION_ID}-{nonce}.pending.json"
    try:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                "16.9",
                "-t",
                "5",
                "-i",
                str(SOURCE),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                str(pending_video),
            ],
            check=True,
            timeout=180,
        )
        pose = extract_pose_sequence(pending_video, target_fps=15)
        if pose.coverage < 0.65:
            raise RuntimeError(f"爵士参考片段人体覆盖率不足：{pose.coverage:.0%}")
        pose.save(pending_sequence)
        pending_manifest.write_text(
            json.dumps(
                {"video": video.name, "sequence": sequence.name},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        pending_video.replace(video)
        pending_sequence.replace(sequence)
        pending_manifest.replace(manifest)
        for pattern in (f"{ACTION_ID}*.mp4", f"{ACTION_ID}*.npz"):
            for previous in OUTPUT_DIR.glob(pattern):
                if previous not in {video, sequence}:
                    previous.unlink(missing_ok=True)
        print(f"ready: assets/references/{video.name}")
        print(f"ready: assets/references/{sequence.name}（coverage={pose.coverage:.0%}）")
        return 0
    finally:
        pending_video.unlink(missing_ok=True)
        pending_sequence.unlink(missing_ok=True)
        pending_manifest.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
