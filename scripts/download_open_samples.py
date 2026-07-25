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

    @property
    def download_url(self) -> str:
        filename = urllib.parse.quote(self.commons_filename, safe="")
        return f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{filename}"


SAMPLES = (
    Sample(
        sample_id="breakdance_6_step",
        commons_filename="6-step example.webm",
        source_page="https://commons.wikimedia.org/wiki/File:6-step_example.webm",
        author="Neil Sweeney",
        license_name="CC BY 3.0",
        license_url="https://creativecommons.org/licenses/by/3.0/",
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
)


def download(sample: Sample, target: Path) -> None:
    request = urllib.request.Request(
        sample.download_url,
        headers={"User-Agent": "DinggeCoachHackathon/1.0 (open sample downloader)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def transcode(source: Path, target: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("未找到 ffmpeg。请先安装 ffmpeg，或使用 --keep-source 跳过转码。")

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
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
        str(target),
    ]
    subprocess.run(command, check=True)


def write_attribution(samples: list[Sample], output_dir: Path) -> None:
    manifest = []
    lines = [
        "# 开放视频样例署名",
        "",
        "以下素材仅用于工程烟雾测试。修改内容：去除音频、转码为 H.264 MP4；未裁剪画面。",
        "",
    ]
    for sample in samples:
        item = asdict(sample)
        item["download_url"] = sample.download_url
        item["local_file"] = f"{sample.sample_id}.mp4"
        manifest.append(item)
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

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")


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
    write_attribution(selected, output_dir)

    if args.dry_run:
        for sample in selected:
            print(f"{sample.sample_id}: {sample.download_url}")
        print(f"署名文件已写入：{output_dir}")
        return 0

    for sample in selected:
        suffix = Path(sample.commons_filename).suffix.lower()
        source = raw_dir / f"{sample.sample_id}{suffix}"
        target = output_dir / f"{sample.sample_id}.mp4"

        if target.exists() and not args.force:
            print(f"[跳过] {target} 已存在")
            continue

        print(f"[下载] {sample.sample_id}")
        try:
            download(sample, source)
            transcode(source, target)
        except Exception as exc:  # noqa: BLE001 - CLI should report per-file failure
            print(f"[失败] {sample.sample_id}: {exc}", file=sys.stderr)
            source.unlink(missing_ok=True)
            return 1
        finally:
            if source.exists() and not args.keep_source:
                source.unlink()

        print(f"[完成] {target}")

    if raw_dir.exists() and not any(raw_dir.iterdir()):
        raw_dir.rmdir()
    print(f"全部样例已准备：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
