#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ACTIONS = ("groove_step", "arm_wave", "cross_step")
LABELS = ("aligned", "timing", "trajectory", "angle")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成动作标定数据目录和拍摄清单")
    parser.add_argument("--root", type=Path, default=Path("assets/evaluation"))
    parser.add_argument("--samples", type=int, default=2, help="每个动作/标签的样本数")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    rows = []
    for action in ACTIONS:
        for label in LABELS:
            for index in range(1, args.samples + 1):
                filename = f"{action}_{label}_{index:02d}.mp4"
                rows.append({"filename": filename, "action": action, "label": label, "recorded": "", "notes": ""})
    manifest = args.root / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "action", "label", "recorded", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"created {manifest} with {len(rows)} planned videos")


if __name__ == "__main__":
    main()
