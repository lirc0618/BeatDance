#!/usr/bin/env python3
"""Download openly licensed motion clips for engineering smoke tests.

These clips validate upload, decoding, MediaPipe extraction, duration checks and
basic alignment. They are not substitutes for the team's same-person,
same-camera calibration set.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class Sample:
    sample_id: str
    commons_filename: str
    source_page: str
    author: str
    license_name: str
    license_url: str
    description: str
    expected_duration_seconds: float
    clip_start_seconds: float | None = None
    clip_duration_seconds: float | None = None

    @property
    def download_url(self) -> str:
        filename = urllib.parse.quote(self.commons_filename, safe="")
        return f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{filename}"


@dataclass(frozen=True)
class ReferenceClip:
    source_sample_id: str
    output_name: str
    start_seconds: float
    duration_seconds: float
    description: str


SAMPLES = (
    Sample(
        sample_id="breakdance_6_step",
        commons_filename="6-step example.gif",
        source_page="https://commons.wikimedia.org/wiki/File:6-step_example.gif",
        author="Neil Sweeney",
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        description="4 秒 breakdance 六步动作；适合测试全身快速动作和地面姿态。",
        expected_duration_seconds=4.0,
    ),
    Sample(
        sample_id="breakdance_2_step",
        commons_filename="Demonstration of a 2-step.webm",
        source_page="https://commons.wikimedia.org/wiki/File:Demonstration_of_a_2-step.webm",
        author="VincaniTV",
        license_name="CC BY 3.0",
        license_url="https://creativecommons.org/licenses/by/3.0/",
        description="6.1 秒 breakdance 两步示范；适合测试节奏与脚步轨迹。",
        expected_duration_seconds=6.1,
    ),
    Sample(
        sample_id="simple_step",
        commons_filename="Simple step demo.ogv",
        source_page="https://commons.wikimedia.org/wiki/File:Simple_step_demo.ogv",
        author="Secarver7",
        license_name="CC BY 3.0",
        license_url="https://creativecommons.org/licenses/by/3.0/",
        description="3.8 秒简单踏步；适合测试普通站立动作与短视频边界。",
        expected_duration_seconds=3.8,
    ),
    Sample(
        sample_id="six_step_tutorial",
        commons_filename="Tutorial breakdance - Six Step.webm",
        source_page="https://commons.wikimedia.org/wiki/File:Tutorial_breakdance_-_Six_Step.webm",
        author="Neil Sweeney",
        license_name="CC BY 3.0",
        license_url="https://creativecommons.org/licenses/by/3.0/",
        description="107 秒 breakdance 六步完整教程；用于测试长 Feed 的任意时刻暂停。",
        expected_duration_seconds=107.0,
    ),
    Sample(
        sample_id="arm_movements_veil",
        commons_filename="Movimientos con velo.webm",
        source_page="https://commons.wikimedia.org/wiki/File:Movimientos_con_velo.webm",
        author="Fabiola Mastache",
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        description="12 秒竖屏手臂运动片段；用于测试手部动作暂停与局部解释。",
        expected_duration_seconds=12.0,
    ),
    Sample(
        sample_id="cha_cha_dance",
        commons_filename="Cha cha cha(Dance).webm",
        source_page="https://commons.wikimedia.org/wiki/File:Cha_cha_cha(Dance).webm",
        author="Wpzhiyilee",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="48 秒恰恰舞片段；用于测试长 Feed 脚步动作的暂停定位。",
        expected_duration_seconds=48.0,
    ),
    Sample(
        sample_id="tendu_tutorial",
        commons_filename="Tendu, ballet technique tutorial.webm",
        source_page="https://commons.wikimedia.org/wiki/File:Tendu,_ballet_technique_tutorial.webm",
        author="Tcshaw427",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="16 秒单人芭蕾脚尖伸展教程；用于测试落点、方向与回位暂停。",
        expected_duration_seconds=16.0,
    ),
    Sample(
        sample_id="ballet_assemble",
        commons_filename="Assemblé dance technique 1080p.webm",
        source_page=(
            "https://commons.wikimedia.org/wiki/"
            "File:Assembl%C3%A9_dance_technique_1080p.webm"
        ),
        author="Tcshaw427",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="3.8 秒单人 Assemblé 动作段；适合测试起跳、并腿落地和动作幅度。",
        expected_duration_seconds=3.8,
        clip_start_seconds=2.6,
        clip_duration_seconds=3.8,
    ),
    Sample(
        sample_id="ballet_balance",
        commons_filename="Balancé, ballet technique tutorial.webm",
        source_page=(
            "https://commons.wikimedia.org/wiki/"
            "File:Balanc%C3%A9,_ballet_technique_tutorial.webm"
        ),
        author="Tcshaw427",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="6.8 秒单人 Balancé 动作段；适合测试左右重心切换和手脚配合。",
        expected_duration_seconds=6.8,
        clip_start_seconds=1.5,
        clip_duration_seconds=6.8,
    ),
    Sample(
        sample_id="ballet_chasse",
        commons_filename="Chassé, ballet technique tutorial.webm",
        source_page=(
            "https://commons.wikimedia.org/wiki/"
            "File:Chass%C3%A9,_ballet_technique_tutorial.webm"
        ),
        author="Tcshaw427",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="3.5 秒单人 Chassé 动作段；适合测试横向移动、并步和落点路线。",
        expected_duration_seconds=3.5,
        clip_start_seconds=2.2,
        clip_duration_seconds=3.5,
    ),
    Sample(
        sample_id="ballet_plie",
        commons_filename="Plié, ballet technique tutorial.webm",
        source_page=(
            "https://commons.wikimedia.org/wiki/"
            "File:Pli%C3%A9,_ballet_technique_tutorial.webm"
        ),
        author="Tcshaw427",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="7 秒单人 Plié 动作段；适合测试膝髋幅度、下沉和回正。",
        expected_duration_seconds=7.0,
        clip_start_seconds=1.5,
        clip_duration_seconds=7.0,
    ),
    Sample(
        sample_id="jazz_pas_de_bourree",
        commons_filename="Pas de bourrée, jazz dance technique.webm",
        source_page=(
            "https://commons.wikimedia.org/wiki/"
            "File:Pas_de_bourr%C3%A9e,_jazz_dance_technique.webm"
        ),
        author="Tcshaw427",
        license_name="CC BY-SA 3.0",
        license_url="https://creativecommons.org/licenses/by-sa/3.0/",
        description="6.4 秒单人爵士 Pas de bourrée 动作段；适合测试交叉步、方向和上肢路线。",
        expected_duration_seconds=6.4,
        clip_start_seconds=1.8,
        clip_duration_seconds=6.4,
    ),
    Sample(
        sample_id="tap_dance_technique",
        commons_filename="Tap Dance Technique.webm",
        source_page="https://commons.wikimedia.org/wiki/File:Tap_Dance_Technique.webm",
        author="Dbuetow",
        license_name="CC BY-SA 4.0",
        license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        description="124 秒单人踢踏舞脚步教程；适合测试局部脚步、节奏与长 Feed 暂停。",
        expected_duration_seconds=124.4,
    ),
)

REFERENCE_CLIPS = (
    ReferenceClip(
        source_sample_id="arm_movements_veil",
        output_name="arm_movements_reference.mp4",
        start_seconds=0.0,
        duration_seconds=5.0,
        description="手臂路线诊断参考；截取源视频 0–5 秒。",
    ),
    ReferenceClip(
        source_sample_id="tendu_tutorial",
        output_name="tendu_reference.mp4",
        start_seconds=4.0,
        duration_seconds=5.0,
        description="Tendu 诊断参考；截取源视频 4–9 秒。",
    ),
)


def download(sample: Sample, target: Path) -> None:
    request = urllib.request.Request(
        sample.download_url,
        headers={"User-Agent": "DinggeCoachHackathon/1.0 (open sample downloader)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def transcode(source: Path, target: Path, sample: Sample) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg，或使用 --keep-source 跳过转码。")

    pending = target.with_name(f".{target.stem}-{uuid4().hex}.pending.mp4")
    try:
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
        ]
        if sample.clip_start_seconds is not None:
            command.extend(["-ss", str(sample.clip_start_seconds)])
        if sample.clip_duration_seconds is not None:
            command.extend(["-t", str(sample.clip_duration_seconds)])
        command.extend(
            [
                "-an",
                "-vf",
                "scale='min(1280,iw)':-2:flags=lanczos,fps=25",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(pending),
            ]
        )
        subprocess.run(command, check=True)
        if not valid_video(pending):
            raise RuntimeError(f"转码结果无效：{target.name}")
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def valid_video(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.is_file() or path.stat().st_size == 0:
        return False
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.returncode == 0 and "video" in completed.stdout


def create_reference_clip(source: Path, target: Path, clip: ReferenceClip) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg，无法生成 Feed 对应的短参考片段。")
    pending = target.with_name(f".{target.stem}-{uuid4().hex}.pending.mp4")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(clip.start_seconds),
                "-t",
                str(clip.duration_seconds),
                "-i",
                str(source),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(pending),
            ],
            check=True,
        )
        if not valid_video(pending):
            raise RuntimeError(f"参考截取结果无效：{target.name}")
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    pending = path.with_name(f".{path.name}-{uuid4().hex}.pending")
    try:
        pending.write_text(content, encoding="utf-8")
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def sample_payload(sample: Sample) -> dict:
    item = {key: value for key, value in asdict(sample).items() if value is not None}
    item["download_url"] = sample.download_url
    item["local_file"] = f"{sample.sample_id}.mp4"
    return item


def write_attribution(samples: list[Sample], output_dir: Path) -> None:
    available = [
        sample
        for sample in samples
        if valid_video(output_dir / f"{sample.sample_id}.mp4")
    ]
    manifest = []
    lines = [
        "# 开放视频样例署名",
        "",
        "以下素材仅用于工程烟雾测试。修改内容：去除音频、转码为 H.264 MP4；部分素材截取单人动作段。",
        "",
    ]
    for sample in available:
        manifest.append(sample_payload(sample))
        lines.extend(
            [
                f"## {sample.sample_id}",
                "",
                f"- 内容：{sample.description}",
                f"- 作者：{sample.author}",
                f"- 来源：{sample.source_page}",
                f"- 许可：{sample.license_name}（{sample.license_url}）",
                "",
            ]
        )
    available_ids = {sample.sample_id for sample in available}
    derived = [
        clip
        for clip in REFERENCE_CLIPS
        if clip.source_sample_id in available_ids
        and valid_video(output_dir / clip.output_name)
    ]
    if derived:
        lines.extend(["## 派生诊断参考片段", ""])
        for clip in derived:
            lines.append(f"- `{clip.output_name}`：{clip.description}")
        lines.append("")

    atomic_write_text(
        output_dir / "catalog.json",
        json.dumps([sample_payload(sample) for sample in samples], ensure_ascii=False, indent=2),
    )
    atomic_write_text(
        output_dir / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    atomic_write_text(output_dir / "ATTRIBUTION.md", "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="assets/samples/open_sources",
        help="输出目录，默认 assets/samples/open_sources",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[sample.sample_id for sample in SAMPLES],
        help="只下载指定样例；可重复传入",
    )
    parser.add_argument("--force", action="store_true", help="覆盖已有文件")
    parser.add_argument(
        "--keep-source", action="store_true", help="保留原始 WebM/OGV 文件"
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印计划，不联网")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_dir = (project_root / args.output).resolve()
    raw_dir = output_dir / "raw"
    selected = [sample for sample in SAMPLES if not args.only or sample.sample_id in args.only]

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        for sample in selected:
            print(f"{sample.sample_id}: {sample.download_url}")
        print(f"将更新完整署名清单：{output_dir}")
        return 0
    for sample in selected:
        suffix = Path(sample.commons_filename).suffix.lower()
        source = raw_dir / f"{sample.sample_id}{suffix}"
        target = output_dir / f"{sample.sample_id}.mp4"

        if target.exists() and not args.force and valid_video(target):
            print(f"[跳过] {target} 已存在")
            continue

        print(f"[下载] {sample.sample_id}")
        try:
            download(sample, source)
            transcode(source, target, sample)
        except Exception as exc:  # noqa: BLE001 - CLI should report per-file failure
            print(f"[失败] {sample.sample_id}: {exc}", file=sys.stderr)
            source.unlink(missing_ok=True)
            write_attribution(list(SAMPLES), output_dir)
            return 1
        finally:
            if source.exists() and not args.keep_source:
                source.unlink()

        print(f"[完成] {target}")

    selected_ids = {sample.sample_id for sample in selected}
    for clip in REFERENCE_CLIPS:
        if clip.source_sample_id not in selected_ids:
            continue
        source = output_dir / f"{clip.source_sample_id}.mp4"
        target = output_dir / clip.output_name
        if target.exists() and not args.force and valid_video(target):
            print(f"[跳过] {target} 已存在")
            continue
        print(f"[截取] {clip.output_name}")
        create_reference_clip(source, target, clip)
        print(f"[完成] {target}")

    if raw_dir.exists() and not any(raw_dir.iterdir()):
        raw_dir.rmdir()
    write_attribution(list(SAMPLES), output_dir)
    print(f"全部样例已准备：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
