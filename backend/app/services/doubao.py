from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from ..schemas import Diagnosis


class DoubaoService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.ark_api_key and self.settings.ark_model)

    async def refine_feedback(
        self,
        diagnosis: Diagnosis,
        action_name: str,
        comparison_image: Path | None = None,
    ) -> str | None:
        if not self.configured:
            return None
        prompt = {
            "任务": (
                "把动作诊断改写成一句小白秒懂的话。先用一个轻松比喻点出问题，"
                "再告诉用户马上怎么做。不要打分，不要术语，不嘲讽用户。"
            ),
            "动作": action_name,
            "阶段": diagnosis.phase,
            "主要问题": diagnosis.primary_error,
            "节奏偏差秒": diagnosis.timing_offset_seconds,
            "轨迹偏差": diagnosis.trajectory_error,
            "角度偏差度": diagnosis.angle_error_degrees,
            "原始建议": diagnosis.priority_feedback,
            "练习": diagnosis.drill,
            "用户主动关注": diagnosis.user_focus,
            "后续搜索词": diagnosis.search_query,
            "输出约束": "中文，50字以内，只输出一句话；像朋友提醒，不像教科书。",
        }
        user_content: Any = json.dumps(prompt, ensure_ascii=False)
        if comparison_image and comparison_image.exists() and self.settings.ark_send_images:
            encoded = base64.b64encode(comparison_image.read_bytes()).decode("ascii")
            user_content = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                },
                {
                    "type": "text",
                    "text": (
                        "左侧是参考动作，右侧是用户动作，红色骨架标出算法定位的重点部位。"
                        "请结合画面核验，只输出一句小白能秒懂、有一点趣味、又能马上照做的话。\n"
                        + json.dumps(prompt, ensure_ascii=False)
                    ),
                },
            ]
        payload: dict[str, Any] = {
            "model": self.settings.ark_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个会说人话的动作搭子。只讲最关键的一处，"
                        "可以用一个轻松比喻，但不要堆梗、羞辱用户或装专业。"
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
            "max_tokens": 100,
        }
        headers = {"Authorization": f"Bearer {self.settings.ark_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.settings.ark_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.ark_base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                return str(data["choices"][0]["message"]["content"]).strip()
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None
