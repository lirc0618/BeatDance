import json
from pathlib import Path

from app.services.coaching_profiles import with_coaching_profile
from app.services.diagnosis import ActionRegistry


def test_featured_dances_each_have_their_own_coaching_language_and_views():
    expected_views = {
        "groove_step": {"镜像跟跳", "手势慢放", "副歌口令", "定点摆拍", "新手半身版"},
        "arm_wave": {"脚步俯拍", "0.5×拆腿", "重拍口令", "落地定格", "扶墙简化"},
        "cross_step": {"上身特写", "节奏口令", "镜像跟摇", "回正定格", "坐姿练肩"},
        "two_step_demo": {"脚下特写", "超慢换腿", "落地节拍", "膝盖定格", "原地简化"},
    }
    stuck_lines: set[str] = set()

    for action_id, views in expected_views.items():
        action = with_coaching_profile({"id": action_id, "name": "任意显示名"})
        assert {item["view_type"] for item in action["tutorials"]} == views
        assert len(action["pause_guides"]) == 3
        stuck_lines.add(action["pause_guides"][0]["likely_stuck_at"])

    assert len(stuck_lines) == 4


def test_display_name_alone_never_overwrites_an_imported_actions_content():
    custom = {
        "id": "my_own_clip",
        "name": "Jumpstyle",
        "description": "我自己的说明",
        "pause_guides": [{"likely_stuck_at": "我自己的卡点"}],
        "tutorials": [],
    }

    assert with_coaching_profile(custom) is custom


def test_existing_catalog_entries_gain_the_named_profile_when_read(tmp_path):
    catalog = tmp_path / "actions.json"
    catalog.write_text(
        json.dumps(
            {
                "actions": [
                    {
                        "id": "groove_step",
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

    action = ActionRegistry(catalog).get("groove_step")

    assert action["pause_guides"][0]["likely_stuck_at"] == "手先营业，胯晚点上线。"
    assert {item["view_type"] for item in action["tutorials"]} == {
        "镜像跟跳",
        "手势慢放",
        "副歌口令",
        "定点摆拍",
        "新手半身版",
    }


def test_failure_type_changes_the_featured_tutorial_selection():
    catalog = Path(__file__).parents[1] / "app" / "data" / "actions.json"
    registry = ActionRegistry(catalog)

    selected = {
        metric: registry.search_tutorials(
            "two_step_demo",
            metric,
            "双腿",
            focus="lower",
            limit=3,
        )
        for metric in ("timing", "trajectory", "angle")
    }

    assert all(items[0].error_type == metric for metric, items in selected.items())
    assert len({frozenset(item.id for item in items) for items in selected.values()}) == 3
