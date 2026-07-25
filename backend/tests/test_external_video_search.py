from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import create_router
from app.config import Settings
from app.services.analyzer import Analyzer
from app.services.external_video_search import ExternalVideoSearch


def test_unconfigured_search_returns_precise_platform_launches():
    search = ExternalVideoSearch(Settings())

    result = asyncio.run(
        search.search(
            action_name="爵士",
            metric="trajectory",
            body_part="双臂",
        )
    )

    assert result.provider == "platform_search"
    assert result.configured is False
    assert result.videos == []
    assert result.query == "爵士 双臂 动作路线 局部拆解 慢动作 教学"
    assert [item.platform for item in result.launches] == ["douyin", "bilibili"]
    assert all("%E7%88%B5%E5%A3%AB" in item.url for item in result.launches)


def test_configured_search_returns_real_douyin_video_cards():
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/oauth/client_token/":
            assert request.method == "POST"
            assert request.headers["content-type"].startswith("application/json")
            assert request.read()
            return httpx.Response(
                200,
                json={
                    "data": {
                        "access_token": "client-token",
                        "expires_in": 7200,
                    },
                    "message": "success",
                },
            )
        assert request.url.path == "/dy_open_api/v2/search/video/"
        assert request.headers["access-token"] == "client-token"
        assert request.url.params["keyword"] == "科目三 脚步 节奏 分拍 慢动作 教学"
        return httpx.Response(
            200,
            json={
                "data": {
                    "data": {
                        "video_list": [
                            {
                                "item_id": "douyin-1",
                                "title": "科目三脚步慢动作，三分钟踩稳",
                                "cover": "https://p3.example.com/cover.jpg",
                                "nickname": "舞蹈课代表",
                                "statistics": {"digg_count": 1288},
                                "link": "https://www.douyin.com/video/123",
                            },
                            {
                                "item_id": "malicious",
                                "title": "伪装的抖音结果",
                                "link": "https://douyin.example.com/phishing",
                            }
                        ]
                    }
                },
                "err_no": 0,
                "message": "success",
            },
        )

    settings = Settings(
        douyin_client_key="client-key",
        douyin_client_secret="client-secret",
    )
    search = ExternalVideoSearch(
        settings,
        transport=httpx.MockTransport(handle),
    )

    result = asyncio.run(
        search.search(
            action_name="科目三",
            metric="timing",
            body_part="脚步",
        )
    )

    assert result.provider == "douyin"
    assert result.configured is True
    assert len(result.videos) == 1
    assert result.videos[0].title == "科目三脚步慢动作，三分钟踩稳"
    assert result.videos[0].creator == "舞蹈课代表"
    assert result.videos[0].like_count == 1288
    assert result.videos[0].url == "https://www.douyin.com/video/123"
    assert len(requests) == 2

    cached = asyncio.run(
        search.search(
            action_name="科目三",
            metric="timing",
            body_part="脚步",
        )
    )
    assert len(cached.videos) == 1
    assert len(requests) == 2


def test_douyin_failure_falls_back_to_platform_search():
    def fail(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "upstream unavailable"})

    search = ExternalVideoSearch(
        Settings(douyin_access_token="temporary-token"),
        transport=httpx.MockTransport(fail),
    )

    result = asyncio.run(
        search.search(
            action_name="Jumpstyle",
            metric="timing",
            body_part="脚步",
        )
    )

    assert result.configured is True
    assert result.provider == "platform_search"
    assert result.videos == []
    assert len(result.launches) == 2
    assert "暂时没回话" in result.message


def test_malformed_success_response_also_falls_back():
    def malformed(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    search = ExternalVideoSearch(
        Settings(douyin_access_token="temporary-token"),
        transport=httpx.MockTransport(malformed),
    )

    result = asyncio.run(
        search.search(
            action_name="摇一摇",
            metric="angle",
            body_part="肩膀",
        )
    )

    assert result.provider == "platform_search"
    assert len(result.launches) == 2


def test_malformed_client_token_response_also_falls_back():
    def malformed(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    search = ExternalVideoSearch(
        Settings(
            douyin_client_key="client-key",
            douyin_client_secret="client-secret",
        ),
        transport=httpx.MockTransport(malformed),
    )

    result = asyncio.run(
        search.search(
            action_name="爱你",
            metric="trajectory",
            body_part="双手",
        )
    )

    assert result.provider == "platform_search"
    assert len(result.launches) == 2


def test_search_api_uses_action_name_and_falls_back_without_credentials(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        tutorial_assets_dir=tmp_path / "tutorials",
    )
    settings.ensure_directories()
    shutil.copy2(
        Path(__file__).parents[1] / "app" / "data" / "actions.json",
        settings.data_dir / "actions.json",
    )
    app = FastAPI()
    app.include_router(
        create_router(settings, Analyzer(settings)),
        prefix=settings.api_prefix,
    )
    client = TestClient(app)

    response = client.get(
        f"{settings.api_prefix}/actions/jazz_demo/related-videos",
        params={"metric": "angle", "body_part": "肩膀"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "爵士 肩膀 定点 造型 姿势 教学"
    assert payload["provider"] == "platform_search"
    assert len(payload["launches"]) == 2


def test_search_api_rejects_unknown_action(tmp_path: Path):
    settings = Settings(
        data_dir=tmp_path / "data",
        feed_dir=tmp_path / "feeds",
        tutorial_assets_dir=tmp_path / "tutorials",
    )
    settings.ensure_directories()
    shutil.copy2(
        Path(__file__).parents[1] / "app" / "data" / "actions.json",
        settings.data_dir / "actions.json",
    )
    app = FastAPI()
    app.include_router(
        create_router(settings, Analyzer(settings)),
        prefix=settings.api_prefix,
    )

    response = TestClient(app).get(
        f"{settings.api_prefix}/actions/not-found/related-videos"
    )

    assert response.status_code == 404

    invalid_limit = TestClient(app).get(
        f"{settings.api_prefix}/actions/jazz_demo/related-videos",
        params={"limit": 99},
    )
    assert invalid_limit.status_code == 422
