from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .diagnosis import ActionRegistry
from .feed_importer import FeedImportSpec

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_library.json"


class SampleLibrary:
    """Expose bundled dance samples without leaking arbitrary server files."""

    def __init__(
        self,
        assets_dir: Path,
        registry: ActionRegistry,
        catalog_path: Path = CATALOG_PATH,
    ) -> None:
        self.assets_dir = assets_dir.resolve()
        self.registry = registry
        self._items = self._load(catalog_path)

    def list(self) -> list[dict[str, Any]]:
        active_ids = {str(item["id"]) for item in self.registry.list()}
        return [
            {
                **item,
                "preview_url": f"/api/v1/sample-library/{item['id']}/video",
                "available": self._path(item).is_file(),
                "imported": item["action_id"] in active_ids,
            }
            for item in self._items.values()
        ]

    def resolve(self, sample_id: str) -> tuple[Path, FeedImportSpec]:
        item, path = self._resolve_item(sample_id)
        return path, FeedImportSpec(
            action_id=str(item["action_id"]),
            name=str(item["name"]),
            pause_at_seconds=float(item["pause_at_seconds"]),
            description=str(item["description"]),
            feed_caption=str(item["description"]),
            creator=str(item["creator"]),
            focus=str(item["focus"]),
        )

    def video_path(self, sample_id: str) -> Path:
        return self._resolve_item(sample_id)[1]

    def _resolve_item(self, sample_id: str) -> tuple[dict[str, Any], Path]:
        try:
            item = self._items[sample_id]
        except KeyError as exc:
            raise KeyError(f"素材库不存在：{sample_id}") from exc
        path = self._path(item)
        if not path.is_file():
            raise FileNotFoundError(f"素材文件尚未准备：{item['filename']}")
        return item, path

    def _path(self, item: dict[str, Any]) -> Path:
        return self.assets_dir / str(item["filename"])

    @staticmethod
    def _load(path: Path) -> dict[str, dict[str, Any]]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items: dict[str, dict[str, Any]] = {}
        for raw_item in payload.get("samples", []):
            item = dict(raw_item)
            sample_id = str(item["id"])
            filename = str(item["filename"])
            if Path(filename).name != filename:
                raise ValueError(f"素材文件名非法：{filename}")
            if sample_id in items:
                raise ValueError(f"素材库存在重复 id：{sample_id}")
            items[sample_id] = item
        return items
