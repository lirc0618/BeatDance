#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

import httpx

PATTERN = re.compile(r"(?P<action>groove_step|arm_wave|cross_step)_(?P<label>timing|trajectory|angle|aligned)_\d+")
FIELDS = [
    "video", "action", "expected", "actual", "status", "correct", "body_part", "confidence",
    "timing_norm", "trajectory_norm", "angle_norm", "timing_seconds", "trajectory_error", "angle_degrees",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="批量评估预设错误与正确动作视频")
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    parser.add_argument("--dir", type=Path, default=Path("assets/evaluation"))
    parser.add_argument("--output", type=Path, default=Path("evaluation.csv"))
    args = parser.parse_args()

    rows: list[dict] = []
    for path in sorted(args.dir.glob("*.mp4")):
        match = PATTERN.match(path.stem)
        if not match:
            print("skip", path.name)
            continue
        expected = match.group("label")
        with path.open("rb") as handle:
            response = httpx.post(
                f"{args.api.rstrip('/')}/analyze",
                data={"action_id": match.group("action"), "session_id": "evaluation"},
                files={"video": (path.name, handle, "video/mp4")},
                timeout=180,
            )
        if response.is_success:
            result = response.json()
            diagnosis = result["diagnosis"]
            status = diagnosis.get("status", "issue_detected")
            actual = "aligned" if status == "aligned" else diagnosis["primary_metric"]
            metric_map = {m["kind"]: m["normalized_score"] for m in diagnosis["metrics"]}
            rows.append({
                "video": path.name,
                "action": match.group("action"),
                "expected": expected,
                "actual": actual,
                "status": status,
                "correct": actual == expected,
                "body_part": diagnosis["body_part"],
                "confidence": diagnosis["confidence"],
                "timing_norm": metric_map.get("timing", ""),
                "trajectory_norm": metric_map.get("trajectory", ""),
                "angle_norm": metric_map.get("angle", ""),
                "timing_seconds": abs(diagnosis["timing_offset_seconds"]),
                "trajectory_error": diagnosis["trajectory_error"],
                "angle_degrees": diagnosis["angle_error_degrees"],
            })
        else:
            rows.append({"video": path.name, "action": match.group("action"), "expected": expected, "actual": "ERROR", "status": "ERROR", "correct": False})
            print(path.name, response.status_code, response.text)

    with args.output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    correct = sum(str(row.get("correct")).lower() == "true" or row.get("correct") is True for row in rows)
    print(f"overall: {correct}/{len(rows)} = {correct/max(len(rows),1):.1%}; saved {args.output}")
    by_action: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_action[row["action"]][(row["expected"], row["actual"])] += 1
    for action, matrix in by_action.items():
        print(f"\n[{action}]")
        for (expected, actual), count in sorted(matrix.items()):
            print(f"  {expected:10s} -> {actual:10s}: {count}")


if __name__ == "__main__":
    main()
