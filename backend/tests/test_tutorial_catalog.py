import json
import subprocess
from pathlib import Path

import pytest

from app.schemas import Tutorial
from app.services import coaching_profiles
from app.services.coaching_profiles import with_coaching_profile
from app.services.tutorial_catalog import load_tutorial_catalog


def test_catalog_has_four_actions_and_twenty_items() -> None:
    grouped = load_tutorial_catalog()

    assert set(grouped) == {"groove_step", "arm_wave", "cross_step", "two_step_demo"}
    assert sum(len(items) for items in grouped.values()) == 20
    assert all(len(items) == 5 for items in grouped.values())
    assert all(len({item["view_type"] for item in items}) >= 3 for items in grouped.values())


def test_catalog_records_local_permission() -> None:
    grouped = load_tutorial_catalog()
    items = [item for action_items in grouped.values() for item in action_items]

    assert all(item["download_policy"] == "local_allowed" for item in items)
    assert all(item["license_status"] == "permission_granted" for item in items)
    assert all(item["license_name"] == "项目已获授权" for item in items)


def test_all_tutorial_recommendations_have_local_video_and_audio() -> None:
    grouped = load_tutorial_catalog()
    root = Path(__file__).parents[2]

    for item in [item for action_items in grouped.values() for item in action_items]:
        local_asset = item["local_asset"]
        assert local_asset == f"assets/tutorials/{item['id']}.mp4"
        assert item["url"] == f"/media/tutorials/{item['id']}.mp4"
        asset = root / local_asset
        assert asset.is_file()
        audio_probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=nw=1:nk=1",
                str(asset),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert audio_probe.stdout.strip() == "aac"


def test_profile_uses_external_tutorial_catalog() -> None:
    action = with_coaching_profile(
        {"id": "groove_step", "name": "爱你", "coaching_profile": "aini"}
    )

    assert len(action["tutorials"]) == 5
    assert action["tutorials"][0]["source_platform"] == "douyin_search"
    Tutorial(**action["tutorials"][0])


def test_profile_does_not_fall_back_to_embedded_tutorials(monkeypatch) -> None:
    monkeypatch.setattr(coaching_profiles, "tutorials_for_action", lambda _action_id: [])

    action = with_coaching_profile(
        {"id": "groove_step", "name": "爱你", "coaching_profile": "aini"}
    )

    assert action["tutorials"] == []


def test_local_asset_must_use_the_tutorial_id_and_directory(tmp_path) -> None:
    catalog = {
        "tutorials": [
            {
                "id": "aini-mirror",
                "action_id": "groove_step",
                "title": "镜像跟跳",
                "error_type": "timing",
                "body_part": "双手",
                "view_type": "镜像跟跳",
                "download_policy": "local_allowed",
                "license_status": "permission_granted",
                "local_asset": "assets/samples/open_sources/ballet_balance.mp4",
            }
        ]
    }
    catalog_path = tmp_path / "tutorial_catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="assets/tutorials/aini-mirror.mp4"):
        load_tutorial_catalog(catalog_path)


def test_local_asset_becomes_a_public_tutorial_video_url(tmp_path) -> None:
    catalog = {
        "tutorials": [
            {
                "id": "aini-mirror",
                "action_id": "groove_step",
                "title": "镜像跟跳",
                "error_type": "timing",
                "body_part": "双手",
                "view_type": "镜像跟跳",
                "download_policy": "local_allowed",
                "license_status": "permission_granted",
                "local_asset": "assets/tutorials/aini-mirror.mp4",
                "url": "",
            }
        ]
    }
    catalog_path = tmp_path / "tutorial_catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

    grouped = load_tutorial_catalog(catalog_path)

    assert grouped["groove_step"][0]["url"] == "/media/tutorials/aini-mirror.mp4"
