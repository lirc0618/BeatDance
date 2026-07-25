from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "tutorial_catalog.json"

_REQUIRED_FIELDS = {
    "id",
    "action_id",
    "title",
    "error_type",
    "body_part",
    "view_type",
    "download_policy",
    "license_status",
}
_ALLOWED_METRICS = {"timing", "trajectory", "angle"}
_ALLOWED_DOWNLOAD_POLICIES = {"link_only", "local_allowed"}
_ALLOWED_LICENSE_STATUSES = {"unverified", "verified_open", "permission_granted"}

_cache_lock = threading.RLock()
_cache_signature: tuple[str, int, int] | None = None
_cache_by_action: dict[str, list[dict[str, Any]]] = {}


def _validate_item(item: dict[str, Any], index: int) -> None:
    missing = sorted(field for field in _REQUIRED_FIELDS if not item.get(field))
    if missing:
        raise ValueError(f"tutorial_catalog 第 {index + 1} 条缺少字段：{', '.join(missing)}")

    metric = str(item["error_type"])
    if metric not in _ALLOWED_METRICS:
        raise ValueError(f"tutorial_catalog 第 {index + 1} 条 error_type 非法：{metric}")

    policy = str(item["download_policy"])
    if policy not in _ALLOWED_DOWNLOAD_POLICIES:
        raise ValueError(f"tutorial_catalog 第 {index + 1} 条 download_policy 非法：{policy}")

    license_status = str(item["license_status"])
    if license_status not in _ALLOWED_LICENSE_STATUSES:
        raise ValueError(f"tutorial_catalog 第 {index + 1} 条 license_status 非法：{license_status}")

    if policy == "local_allowed" and license_status not in {
        "verified_open",
        "permission_granted",
    }:
        raise ValueError(
            f"tutorial_catalog 第 {index + 1} 条允许本地保存，但许可尚未核验"
        )

    local_asset = str(item.get("local_asset", "")).strip()
    if local_asset:
        expected_asset = f"assets/tutorials/{item['id']}.mp4"
        if local_asset != expected_asset:
            raise ValueError(
                f"tutorial_catalog 第 {index + 1} 条 local_asset 应为："
                f"{expected_asset}"
            )


def load_tutorial_catalog(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load and validate the external tutorial catalog, grouped by action ID."""
    catalog_path = (path or CATALOG_PATH).resolve()
    if not catalog_path.is_file():
        return {}

    stat = catalog_path.stat()
    signature = (str(catalog_path), stat.st_mtime_ns, stat.st_size)

    global _cache_signature, _cache_by_action
    with _cache_lock:
        if signature == _cache_signature:
            return deepcopy(_cache_by_action)

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        raw_items = payload.get("tutorials", [])
        if not isinstance(raw_items, list):
            raise ValueError("tutorial_catalog.tutorials 必须是数组")

        seen_ids: set[str] = set()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValueError(f"tutorial_catalog 第 {index + 1} 条必须是对象")
            item = dict(raw_item)
            _validate_item(item, index)

            tutorial_id = str(item["id"])
            if tutorial_id in seen_ids:
                raise ValueError(f"tutorial_catalog 存在重复 id：{tutorial_id}")
            seen_ids.add(tutorial_id)

            action_id = str(item.pop("action_id"))
            grouped.setdefault(action_id, []).append(item)

        _cache_signature = signature
        _cache_by_action = grouped
        return deepcopy(grouped)


def tutorials_for_action(action_id: str, path: Path | None = None) -> list[dict[str, Any]]:
    return load_tutorial_catalog(path).get(action_id, [])
