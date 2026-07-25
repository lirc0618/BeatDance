from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "backend" / "app" / "data" / "tutorial_catalog.json"

REQUIRED_FIELDS = {
    "id",
    "action_id",
    "title",
    "error_type",
    "body_part",
    "view_type",
    "download_policy",
    "license_status",
}
ALLOWED_METRICS = {"timing", "trajectory", "angle"}
ALLOWED_POLICIES = {"link_only", "local_allowed"}
ALLOWED_LICENSES = {"unverified", "verified_open", "permission_granted"}


def _looks_like_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate(
    catalog_path: Path,
    *,
    expected_actions: int,
    min_per_action: int,
    strict_sources: bool,
) -> tuple[list[str], list[str], dict[str, Any]]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    items = payload.get("tutorials")
    if not isinstance(items, list):
        return ["tutorials 必须是数组"], [], {}

    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metric_counts: Counter[str] = Counter()
    view_counts: Counter[str] = Counter()
    license_counts: Counter[str] = Counter()

    for index, raw_item in enumerate(items, start=1):
        if not isinstance(raw_item, dict):
            errors.append(f"第 {index} 条不是对象")
            continue
        item = raw_item
        missing = sorted(field for field in REQUIRED_FIELDS if not item.get(field))
        if missing:
            errors.append(f"第 {index} 条缺少字段：{', '.join(missing)}")
            continue

        tutorial_id = str(item["id"])
        if tutorial_id in seen_ids:
            errors.append(f"重复 id：{tutorial_id}")
        seen_ids.add(tutorial_id)

        action_id = str(item["action_id"])
        by_action[action_id].append(item)

        metric = str(item["error_type"])
        metric_counts[metric] += 1
        if metric not in ALLOWED_METRICS:
            errors.append(f"{tutorial_id}: error_type 非法：{metric}")

        view_type = str(item["view_type"])
        view_counts[view_type] += 1

        policy = str(item["download_policy"])
        if policy not in ALLOWED_POLICIES:
            errors.append(f"{tutorial_id}: download_policy 非法：{policy}")

        license_status = str(item["license_status"])
        license_counts[license_status] += 1
        if license_status not in ALLOWED_LICENSES:
            errors.append(f"{tutorial_id}: license_status 非法：{license_status}")

        source_url = str(item.get("source_url", "")).strip()
        if source_url and not _looks_like_http_url(source_url):
            errors.append(f"{tutorial_id}: source_url 不是有效 HTTP(S) 地址")
        if not source_url:
            message = f"{tutorial_id}: 尚未登记原始来源链接"
            (errors if strict_sources else warnings).append(message)

        if license_status == "unverified":
            message = f"{tutorial_id}: 许可状态尚未核验"
            (errors if strict_sources else warnings).append(message)

        if policy == "local_allowed":
            if license_status not in {"verified_open", "permission_granted"}:
                errors.append(f"{tutorial_id}: 本地保存策略与许可状态冲突")
            local_asset = str(item.get("local_asset", "")).strip()
            if not local_asset:
                warnings.append(f"{tutorial_id}: 已允许本地保存，但尚未登记本地文件路径")
            else:
                expected_asset = f"assets/tutorials/{tutorial_id}.mp4"
                if local_asset != expected_asset:
                    errors.append(
                        f"{tutorial_id}: local_asset 应为：{expected_asset}"
                    )
                elif not (ROOT / local_asset).is_file():
                    errors.append(f"{tutorial_id}: 本地文件不存在：{local_asset}")

    if len(by_action) != expected_actions:
        errors.append(f"动作数为 {len(by_action)}，期望 {expected_actions}")

    for action_id, action_items in sorted(by_action.items()):
        if len(action_items) < min_per_action:
            errors.append(
                f"动作 {action_id} 仅有 {len(action_items)} 条内容，至少需要 {min_per_action} 条"
            )
        if len({str(item["view_type"]) for item in action_items}) < min(3, min_per_action):
            errors.append(f"动作 {action_id} 的教学视角不足 3 种")

    summary = {
        "actions": {action_id: len(action_items) for action_id, action_items in sorted(by_action.items())},
        "total": len(items),
        "metrics": dict(metric_counts),
        "views": dict(view_counts),
        "licenses": dict(license_counts),
    }
    return errors, warnings, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 BeatMatch 教学内容矩阵与许可元数据")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--expected-actions", type=int, default=4)
    parser.add_argument("--min-per-action", type=int, default=5)
    parser.add_argument(
        "--strict-sources",
        action="store_true",
        help="将缺少原始链接或未核验许可视为错误",
    )
    args = parser.parse_args()

    errors, warnings, summary = validate(
        args.catalog,
        expected_actions=args.expected_actions,
        min_per_action=args.min_per_action,
        strict_sources=args.strict_sources,
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")

    if errors:
        print(f"内容矩阵校验失败：{len(errors)} 个错误，{len(warnings)} 个警告")
        return 1
    print(f"内容矩阵结构通过：{summary.get('total', 0)} 条内容，{len(warnings)} 个待补项")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
