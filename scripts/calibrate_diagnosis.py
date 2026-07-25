#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections import defaultdict
from pathlib import Path

METRICS = ("timing", "trajectory", "angle")


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    clean = []
    for row in rows:
        try:
            row["values"] = {metric: float(row[f"{metric}_norm"]) for metric in METRICS}
        except (ValueError, KeyError):
            continue
        clean.append(row)
    return clean


def predict(row: dict, weights: dict[str, float], aligned_threshold: float) -> str:
    weighted = {metric: row["values"][metric] * weights[metric] for metric in METRICS}
    metric = max(weighted, key=weighted.get)
    return "aligned" if max(weighted.values()) < aligned_threshold else metric


def main() -> None:
    parser = argparse.ArgumentParser(description="根据 evaluation.csv 网格搜索三类诊断权重与对齐阈值")
    parser.add_argument("csv", type=Path, nargs="?", default=Path("evaluation.csv"))
    parser.add_argument("--output", type=Path, default=Path("diagnosis-calibration.json"))
    args = parser.parse_args()
    rows = load_rows(args.csv)
    if not rows:
        raise SystemExit("没有可用评估数据")

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["action"]].append(row)

    output = {}
    grid_weights = [0.8, 0.9, 1.0, 1.1, 1.2]
    grid_thresholds = [0.14, 0.18, 0.22, 0.26, 0.30, 0.34]
    for action, samples in grouped.items():
        best = None
        for values in itertools.product(grid_weights, repeat=3):
            weights = dict(zip(METRICS, values))
            for threshold in grid_thresholds:
                predictions = [predict(row, weights, threshold) for row in samples]
                accuracy = sum(pred == row["expected"] for pred, row in zip(predictions, samples)) / len(samples)
                # 同分时偏好更接近 1 的权重，减少过拟合。
                regularization = sum(abs(value - 1.0) for value in values)
                candidate = (accuracy, -regularization, -abs(threshold - 0.22), weights, threshold)
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
        assert best is not None
        accuracy, _, _, weights, threshold = best
        output[action] = {
            "weights": weights,
            "aligned_threshold": threshold,
            "training_samples": len(samples),
            "training_accuracy": round(accuracy, 4),
        }
        print(f"{action}: accuracy={accuracy:.1%}, weights={weights}, aligned_threshold={threshold}")

    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {args.output}")


if __name__ == "__main__":
    main()
