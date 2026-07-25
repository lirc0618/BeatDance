import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

import download_open_samples as downloader


def test_manifest_only_lists_materialized_videos(tmp_path, monkeypatch):
    sample = downloader.SAMPLES[0]
    (tmp_path / f"{sample.sample_id}.mp4").write_bytes(b"video")
    monkeypatch.setattr(
        downloader,
        "valid_video",
        lambda path: path.is_file() and path.stat().st_size > 0,
    )

    downloader.write_attribution(list(downloader.SAMPLES), tmp_path)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    attribution = (tmp_path / "ATTRIBUTION.md").read_text(encoding="utf-8")
    assert [item["sample_id"] for item in manifest] == [sample.sample_id]
    assert len(catalog) == len(downloader.SAMPLES)
    assert sample.source_page in attribution
    assert downloader.SAMPLES[1].source_page not in attribution
    assert not list(tmp_path.glob(".*.pending"))
