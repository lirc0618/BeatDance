#!/usr/bin/env python3
"""Build compact, audible tutorial variants from the five authorized demo dances."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "assets" / "samples" / "open_sources"
OUTPUT_DIR = ROOT / "assets" / "tutorials"


@dataclass(frozen=True)
class TutorialVariant:
    tutorial_id: str
    source_name: str
    start_seconds: float
    duration_seconds: float
    mode: str


VARIANTS = (
    TutorialVariant("aini-mirror", "爱你.MP4", 3.0, 11.0, "mirror"),
    TutorialVariant("aini-hands", "爱你.MP4", 5.0, 9.0, "upper"),
    TutorialVariant("aini-chorus", "爱你.MP4", 6.0, 8.0, "beat"),
    TutorialVariant("aini-freeze", "爱你.MP4", 7.0, 7.0, "freeze"),
    TutorialVariant("aini-easy", "爱你.MP4", 4.0, 10.0, "easy"),
    TutorialVariant("kemusan-feet", "科目三.MP4", 7.0, 10.0, "lower"),
    TutorialVariant("kemusan-slow", "科目三.MP4", 8.0, 13.0, "slow"),
    TutorialVariant("kemusan-beat", "科目三.MP4", 9.0, 8.0, "beat"),
    TutorialVariant("kemusan-freeze", "科目三.MP4", 10.0, 8.0, "freeze"),
    TutorialVariant("kemusan-easy", "科目三.MP4", 6.0, 12.0, "easy"),
    TutorialVariant("shake-upper", "摇一摇.MP4", 2.0, 9.0, "upper"),
    TutorialVariant("shake-beat", "摇一摇.MP4", 3.0, 8.0, "beat"),
    TutorialVariant("shake-mirror", "摇一摇.MP4", 2.0, 11.0, "mirror"),
    TutorialVariant("shake-freeze", "摇一摇.MP4", 4.0, 7.0, "freeze"),
    TutorialVariant("shake-easy", "摇一摇.MP4", 2.0, 9.0, "easy"),
    TutorialVariant("jumpstyle-feet", "jumpstyle.MP4", 3.0, 10.0, "lower"),
    TutorialVariant("jumpstyle-slow", "jumpstyle.MP4", 4.0, 12.0, "slow"),
    TutorialVariant("jumpstyle-beat", "jumpstyle.MP4", 5.0, 9.0, "beat"),
    TutorialVariant("jumpstyle-freeze", "jumpstyle.MP4", 6.0, 8.0, "freeze"),
    TutorialVariant("jumpstyle-easy", "jumpstyle.MP4", 3.0, 11.0, "easy"),
    TutorialVariant("jazz-mirror", "爵士.MP4", 8.0, 10.0, "mirror"),
    TutorialVariant("jazz-upper", "爵士.MP4", 12.0, 8.0, "upper"),
    TutorialVariant("jazz-beat", "爵士.MP4", 15.0, 9.0, "beat"),
    TutorialVariant("jazz-freeze", "爵士.MP4", 19.0, 8.0, "freeze"),
    TutorialVariant("jazz-easy", "爵士.MP4", 10.0, 11.0, "easy"),
)


def filters_for(variant: TutorialVariant) -> tuple[float, str, str]:
    target_duration = variant.duration_seconds
    speed = {"slow": 0.55, "easy": 0.72, "beat": 0.85}.get(variant.mode, 1.0)
    freeze_seconds = 1.25 if variant.mode == "freeze" else 0.0
    input_duration = max(2.0, (target_duration - freeze_seconds) * speed)

    video_filters: list[str] = []
    if variant.mode == "upper":
        video_filters.append("crop=iw:ih*0.64:0:0")
    elif variant.mode == "lower":
        video_filters.append("crop=iw:ih*0.64:0:ih*0.36")
    video_filters.append(
        "scale=360:640:force_original_aspect_ratio=decrease,"
        "pad=360:640:(ow-iw)/2:(oh-ih)/2:black"
    )
    if variant.mode == "mirror":
        video_filters.append("hflip")
    if speed != 1.0:
        video_filters.append(f"setpts=PTS/{speed}")
    if freeze_seconds:
        video_filters.append(
            f"tpad=stop_mode=clone:stop_duration={freeze_seconds}"
        )
    video_filters.append("fps=24")

    audio_filters = [f"atempo={speed}" if speed != 1.0 else "anull"]
    if freeze_seconds:
        audio_filters.append(f"apad=pad_dur={freeze_seconds}")
    return input_duration, ",".join(video_filters), ",".join(audio_filters)


def build(variant: TutorialVariant, *, force: bool) -> None:
    source = SOURCE_DIR / variant.source_name
    target = OUTPUT_DIR / f"{variant.tutorial_id}.mp4"
    if playable_with_audio(target) and not force:
        return
    if not source.is_file():
        raise FileNotFoundError(f"缺少授权源视频：{source}")
    input_duration, video_filter, audio_filter = filters_for(variant)
    pending = target.with_name(f".{target.stem}-{uuid4().hex}.pending.mp4")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(variant.start_seconds),
                "-t",
                str(input_duration),
                "-i",
                str(source),
                "-filter_complex",
                f"[0:v]{video_filter}[v];[0:a]{audio_filter}[a]",
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "29",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(pending),
            ],
            check=True,
            timeout=180,
        )
        if not playable_with_audio(pending):
            raise RuntimeError(f"生成的视频缺少画面或声音：{variant.tutorial_id}")
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def playable_with_audio(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return {"video", "audio"}.issubset(set(probe.stdout.splitlines()))


def main() -> int:
    parser = argparse.ArgumentParser(description="生成对拍本地教学拆解视频")
    parser.add_argument("--force", action="store_true", help="覆盖已经生成的视频")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("未找到 ffmpeg")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        build(variant, force=args.force)
        print(f"ready: assets/tutorials/{variant.tutorial_id}.mp4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
