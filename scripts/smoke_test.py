#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


from http_client import build_http_client


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
    with build_http_client(timeout=180, api_url=args.api) as client, args.video.open("rb") as handle:
        response = client.post(
            f"{args.api.rstrip('/')}/analyze",
            data=data,
            files={"video": (args.video.name, handle, "video/mp4")},
        )
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    response.raise_for_status()


if __name__ == "__main__":
    main()
