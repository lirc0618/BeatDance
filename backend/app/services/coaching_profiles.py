from __future__ import annotations

from copy import deepcopy
from typing import Any

from .tutorial_catalog import tutorials_for_action

PROFILES: dict[str, dict[str, Any]] = {
    "aini": {
        "description": "手势要甜，拍点要脆，点到就收。",
        "feed_caption": "甜妹感不是甩大，是每一下都刚好。",
        "pause_guides": [
            {
                "until_ratio": 0.34,
                "phase": "手势开机",
                "likely_stuck_at": "手先营业，胯晚点上线。",
                "watch_for": "口令：手到，胯到。",
                "suggested_focus": "upper",
                "metric": "timing",
                "body_part": "双手",
            },
            {
                "until_ratio": 0.67,
                "phase": "副歌上糖",
                "likely_stuck_at": "甜不是甩大，点到就收。",
                "watch_for": "口令：点、收、换边。",
                "suggested_focus": "upper",
                "metric": "trajectory",
                "body_part": "双手",
            },
            {
                "until_ratio": 1.0,
                "phase": "收尾定点",
                "likely_stuck_at": "笑容可以松，拍子不能掉。",
                "watch_for": "口令：停住半拍。",
                "suggested_focus": "upper",
                "metric": "angle",
                "body_part": "双臂",
            },
        ],
    },
    "kemusan": {
        "description": "脚下点火、重心换挡，落地还得弹。",
        "feed_caption": "脚在蹦迪，重心可别还在加载。",
        "pause_guides": [
            {
                "until_ratio": 0.34,
                "phase": "脚步点火",
                "likely_stuck_at": "脚在蹦迪，重心还在加载。",
                "watch_for": "口令：点地，跟重心。",
                "suggested_focus": "lower",
                "metric": "timing",
                "body_part": "双脚",
            },
            {
                "until_ratio": 0.67,
                "phase": "摆胯换挡",
                "likely_stuck_at": "胯别画大饼，换边要脆。",
                "watch_for": "口令：左、右、秒切。",
                "suggested_focus": "lower",
                "metric": "trajectory",
                "body_part": "髋部",
            },
            {
                "until_ratio": 1.0,
                "phase": "弹回收步",
                "likely_stuck_at": "落地别坐死，弹回来。",
                "watch_for": "口令：落、弹、收。",
                "suggested_focus": "lower",
                "metric": "angle",
                "body_part": "双腿",
            },
        ],
    },
    "shake": {
        "description": "肩胯一起联网，摇得松但轴心不跑。",
        "feed_caption": "摇不是散架，松弛感也有主心骨。",
        "pause_guides": [
            {
                "until_ratio": 0.34,
                "phase": "肩膀开机",
                "likely_stuck_at": "肩开机了，胯还没联网。",
                "watch_for": "口令：肩带胯。",
                "suggested_focus": "upper",
                "metric": "timing",
                "body_part": "双肩",
            },
            {
                "until_ratio": 0.67,
                "phase": "左右换边",
                "likely_stuck_at": "摇不是散架，轴心别跑路。",
                "watch_for": "口令：摇两边，人留中间。",
                "suggested_focus": "auto",
                "metric": "trajectory",
                "body_part": "躯干",
            },
            {
                "until_ratio": 1.0,
                "phase": "回正收尾",
                "likely_stuck_at": "回正要收，别把惯性带回家。",
                "watch_for": "口令：摇、停、回中。",
                "suggested_focus": "auto",
                "metric": "angle",
                "body_part": "躯干",
            },
        ],
    },
    "jumpstyle": {
        "description": "腿快、点准、落地还能接着弹。",
        "feed_caption": "腿像弹幕一样刷过去，落地还得稳。",
        "pause_guides": [
            {
                "until_ratio": 0.34,
                "phase": "踢腿点火",
                "likely_stuck_at": "腿是弹幕，落地得卡点。",
                "watch_for": "口令：踢、落、弹。",
                "suggested_focus": "lower",
                "metric": "timing",
                "body_part": "右腿",
            },
            {
                "until_ratio": 0.67,
                "phase": "前后换腿",
                "likely_stuck_at": "换腿别排队，前后脚要秒切。",
                "watch_for": "口令：前脚走，后脚到。",
                "suggested_focus": "lower",
                "metric": "trajectory",
                "body_part": "双腿",
            },
            {
                "until_ratio": 1.0,
                "phase": "落地续航",
                "likely_stuck_at": "脚别焊地上，落下就弹走。",
                "watch_for": "口令：轻落，快弹。",
                "suggested_focus": "lower",
                "metric": "angle",
                "body_part": "双腿",
            },
        ],
    }
}


FEATURED_PROFILE_BY_ACTION_ID = {
    "groove_step": "aini",
    "arm_wave": "kemusan",
    "cross_step": "shake",
    "two_step_demo": "jumpstyle",
}


def with_coaching_profile(action: dict[str, Any]) -> dict[str, Any]:
    """Return an action with its named coaching personality applied."""

    profile_key = action.get("coaching_profile") or FEATURED_PROFILE_BY_ACTION_ID.get(
        str(action.get("id", ""))
    )
    profile = PROFILES.get(str(profile_key))
    if profile is None:
        return action
    enriched = {**action, **deepcopy(profile)}
    enriched["tutorials"] = tutorials_for_action(str(action.get("id", "")))
    return enriched
