#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    parser.add_argument("--action", required=True)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--baseline")
    args = parser.parse_args()
    data = {"action_id": args.action, "session_id": "smoke-test"}
    if args.baseline:
        data["baseline_analysis_id"] = args.baseline
    with args.video.open("rb") as handle:
        response = httpx.post(
            f"{args.api.rstrip('/')}/analyze",
            data=data,
            files={"video": (args.video.name, handle, "video/mp4")},
            timeout=180,
        )
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    response.raise_for_status()


if __name__ == "__main__":
    main()
