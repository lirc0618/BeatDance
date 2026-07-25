#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


from http_client import build_http_client


def main() -> None:
    parser = argparse.ArgumentParser(description="上传定格教练参考动作视频")
    parser.add_argument("--api", required=True, help="例如 http://localhost:8000/api/v1")
    parser.add_argument("--token", required=True)
    parser.add_argument("--action", required=True, choices=["groove_step", "arm_wave", "cross_step"])
    parser.add_argument("--video", required=True, type=Path)
    args = parser.parse_args()

    with build_http_client(timeout=180, api_url=args.api) as client, args.video.open("rb") as handle:
        response = client.post(
            f"{args.api.rstrip('/')}/actions/{args.action}/reference",
            files={"video": (args.video.name, handle, "video/mp4")},
            headers={"X-Admin-Token": args.token},
        )
    print(response.status_code, response.text)
    response.raise_for_status()


if __name__ == "__main__":
    main()
