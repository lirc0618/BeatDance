import json

from app.services.coaching_profiles import with_coaching_profile
from app.services.diagnosis import ActionRegistry


def test_featured_dances_each_have_their_own_coaching_language_and_views():
    expected_views = {
        "爱你": {"镜像跟跳", "手势慢放", "副歌口令"},
        "科目三": {"脚步俯拍", "0.5×拆腿", "重拍口令"},
        "摇一摇": {"上身特写", "节奏口令", "镜像跟摇"},
        "Jumpstyle": {"脚下特写", "超慢换腿", "落地节拍"},
    }
    stuck_lines: set[str] = set()

    for name, views in expected_views.items():
        action = with_coaching_profile({"id": "dance", "name": name})
        assert {item["view_type"] for item in action["tutorials"]} == views
        assert len(action["pause_guides"]) == 3
        stuck_lines.add(action["pause_guides"][0]["likely_stuck_at"])

    assert len(stuck_lines) == 4


def test_existing_catalog_entries_gain_the_named_profile_when_read(tmp_path):
    catalog = tmp_path / "actions.json"
    catalog.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "id": "aini",
                        "name": "爱你",
                        "description": "旧的通用说明",
                        "pause_guides": [],
                        "tutorials": [],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    action = ActionRegistry(catalog).get("aini")

    assert action["pause_guides"][0]["likely_stuck_at"] == "手先营业，胯晚点上线。"
    assert {item["view_type"] for item in action["tutorials"]} == {
        "镜像跟跳",
        "手势慢放",
        "副歌口令",
    }
