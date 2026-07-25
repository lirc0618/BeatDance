#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from http_client import build_http_client


def main() -> int:
    parser = argparse.ArgumentParser(
        description="导入或替换任意 Feed 视频，并自动准备诊断参考",
    )
    parser.add_argument("video", type=Path, help="本地 MP4/MOV/WEBM 等视频")
    parser.add_argument("--id", required=True, dest="action_id", help="稳定动作 ID")
    parser.add_argument("--name", required=True, help="页面显示名称")
    parser.add_argument("--pause-at", type=float, help="用于抽取参考的清晰动作秒数")
    parser.add_argument("--description", default="")
    parser.add_argument("--caption", default="", help="Feed 卡片主文案")
    parser.add_argument("--creator", default="自定义素材")
    parser.add_argument(
        "--focus",
        choices=["auto", "upper", "lower", "timing"],
        default="auto",
        help="默认关注：自动、上肢、下肢或拍点",
    )
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8000/api/v1",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("ADMIN_TOKEN", "change-me"),
    )
    args = parser.parse_args()

    if not args.video.is_file():
        parser.error(f"视频不存在：{args.video}")

    data = {
        "action_id": args.action_id,
        "name": args.name,
        "description": args.description,
        "feed_caption": args.caption,
        "creator": args.creator,
        "focus": args.focus,
    }
    if args.pause_at is not None:
        data["pause_at_seconds"] = str(args.pause_at)

    api = args.api.rstrip("/")
    with (
        build_http_client(timeout=360, api_url=api) as client,
        args.video.open("rb") as handle,
    ):
        response = client.post(
            f"{api}/actions/import",
            data=data,
            files={
                "video": (
                    args.video.name,
                    handle,
                    "application/octet-stream",
                )
            },
            headers={"X-Admin-Token": args.token},
        )

    payload = response.json()
    if not response.is_success:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        response.raise_for_status()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    verb = "新增" if payload["created"] else "替换"
    print(f"\n{verb}完成：{payload['action']['name']}（{payload['action']['id']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
