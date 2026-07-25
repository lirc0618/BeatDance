from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from ..config import Settings
from ..schemas import (
    ExternalVideo,
    ExternalVideoSearchResponse,
    MetricKind,
    SearchLaunch,
)


class ExternalVideoSearch:
    """Search related teaching videos without coupling them to local tutorial assets."""

    _QUERY_HINTS: dict[MetricKind, str] = {
        "timing": "节奏 分拍 慢动作 教学",
        "trajectory": "动作路线 局部拆解 慢动作 教学",
        "angle": "定点 造型 姿势 教学",
    }

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self._cached_token = ""
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()
        self._quota_lock = asyncio.Lock()
        self._search_slots = asyncio.Semaphore(4)
        self._video_cache: dict[
            tuple[str, int],
            tuple[float, list[ExternalVideo]],
        ] = {}
        self._search_times: deque[float] = deque()

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.douyin_access_token
            or (
                self.settings.douyin_client_key
                and self.settings.douyin_client_secret
            )
        )

    async def search(
        self,
        *,
        action_name: str,
        metric: MetricKind = "trajectory",
        body_part: str = "",
        limit: int = 6,
    ) -> ExternalVideoSearchResponse:
        query = self.build_query(action_name, metric, body_part)
        launches = self._platform_launches(query)
        if not self.configured:
            return ExternalVideoSearchResponse(
                query=query,
                provider="platform_search",
                configured=False,
                launches=launches,
                message="还没接入抖音搜索权限，先用精准关键词打开平台结果。",
            )

        try:
            videos = await self._cached_douyin_search(query, limit)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return ExternalVideoSearchResponse(
                query=query,
                provider="platform_search",
                configured=True,
                launches=launches,
                message="抖音搜索暂时没回话，已切到平台搜索入口。",
            )

        return ExternalVideoSearchResponse(
            query=query,
            provider="douyin",
            configured=True,
            videos=videos,
            launches=launches,
            message=(
                f"搜到 {len(videos)} 条外部教学视频。"
                if videos
                else "暂时没有命中，换个平台继续搜。"
            ),
        )

    @classmethod
    def build_query(
        cls,
        action_name: str,
        metric: MetricKind,
        body_part: str,
    ) -> str:
        terms = [
            action_name.strip(),
            body_part.strip(),
            cls._QUERY_HINTS[metric],
        ]
        return " ".join(item for item in terms if item)

    @staticmethod
    def _platform_launches(query: str) -> list[SearchLaunch]:
        encoded = quote(query, safe="")
        return [
            SearchLaunch(
                platform="douyin",
                label="去抖音搜同款",
                url=f"https://www.douyin.com/search/{encoded}",
            ),
            SearchLaunch(
                platform="bilibili",
                label="去 B 站看教程",
                url=f"https://search.bilibili.com/all?keyword={encoded}",
            ),
        ]

    async def _search_douyin(self, query: str, limit: int) -> list[ExternalVideo]:
        token = await self._access_token()
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=self.settings.douyin_timeout_seconds,
        ) as client:
            response = await client.get(
                self.settings.douyin_search_url,
                headers={
                    "access-token": token,
                    "content-type": "application/json",
                },
                params={
                    "keyword": query,
                    "count": max(1, min(limit, 10)),
                    "cursor": 0,
                    "device_id": self.settings.douyin_device_id,
                    "sort_type": 0,
                    "publish_time": 0,
                },
            )
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, Mapping):
            raise TypeError("抖音搜索返回格式异常")
        error_number = payload.get("err_no", 0)
        if error_number not in (0, "0", None):
            raise ValueError(payload.get("message", "抖音搜索失败"))
        data = payload.get("data", {})
        nested_data = data.get("data", {}) if isinstance(data, Mapping) else {}
        raw_videos = (
            nested_data.get("video_list")
            or (data.get("video_list") if isinstance(data, Mapping) else None)
            or []
        )
        return [
            self._video_from_payload(item)
            for item in raw_videos[:limit]
            if isinstance(item, Mapping) and self._video_url(item)
        ]

    async def _cached_douyin_search(
        self,
        query: str,
        limit: int,
    ) -> list[ExternalVideo]:
        key = (query, limit)
        now = time.monotonic()
        cached = self._video_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

        # 额度检查只占用一个极短临界区；外部网络请求不持有全局锁。
        async with self._quota_lock:
            now = time.monotonic()
            cached = self._video_cache.get(key)
            if cached and cached[0] > now:
                return cached[1]
            while self._search_times and self._search_times[0] <= now - 60:
                self._search_times.popleft()
            if (
                len(self._search_times)
                >= max(1, self.settings.douyin_search_max_per_minute)
            ):
                raise ValueError("外部视频搜索过于频繁")
            self._search_times.append(now)
        try:
            await asyncio.wait_for(self._search_slots.acquire(), timeout=0.25)
        except TimeoutError as exc:
            raise ValueError("外部视频搜索正在排队") from exc
        try:
            videos = await self._search_douyin(query, limit)
        finally:
            self._search_slots.release()

        now = time.monotonic()
        if len(self._video_cache) >= 256:
            expired = [
                cache_key
                for cache_key, (expires_at, _) in self._video_cache.items()
                if expires_at <= now
            ]
            for cache_key in expired:
                self._video_cache.pop(cache_key, None)
            if len(self._video_cache) >= 256:
                self._video_cache.pop(next(iter(self._video_cache)))
        self._video_cache[key] = (
            now + max(0, self.settings.douyin_search_cache_seconds),
            videos,
        )
        return videos

    async def _access_token(self) -> str:
        if self.settings.douyin_access_token:
            return self.settings.douyin_access_token
        if self._cached_token and time.monotonic() < self._token_expires_at:
            return self._cached_token

        async with self._token_lock:
            if self._cached_token and time.monotonic() < self._token_expires_at:
                return self._cached_token
            async with httpx.AsyncClient(
                transport=self.transport,
                timeout=self.settings.douyin_timeout_seconds,
            ) as client:
                response = await client.post(
                    self.settings.douyin_token_url,
                    headers={"content-type": "application/json"},
                    json={
                        "grant_type": "client_credential",
                        "client_key": self.settings.douyin_client_key,
                        "client_secret": self.settings.douyin_client_secret,
                    },
                )
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, Mapping):
                raise TypeError("抖音 token 返回格式异常")
            data = payload.get("data", {})
            if not isinstance(data, Mapping):
                raise TypeError("抖音 token 数据格式异常")
            token = str(data.get("access_token") or "")
            if not token:
                raise ValueError(payload.get("message", "未获取到抖音 access token"))
            expires_in = max(60, int(data.get("expires_in") or 7200))
            self._cached_token = token
            self._token_expires_at = time.monotonic() + expires_in - 30
            return token

    @classmethod
    def _video_from_payload(cls, item: Mapping[str, Any]) -> ExternalVideo:
        statistics = item.get("statistics")
        likes = (
            statistics.get("digg_count", 0)
            if isinstance(statistics, Mapping)
            else 0
        )
        return ExternalVideo(
            id=str(item.get("item_id") or item.get("video_id") or cls._video_url(item)),
            title=str(item.get("title") or "抖音相关教学"),
            cover_url=str(item.get("cover") or item.get("cover_url") or ""),
            creator=str(item.get("nickname") or item.get("author_name") or ""),
            url=cls._video_url(item),
            like_count=max(0, int(likes or 0)),
        )

    @staticmethod
    def _video_url(item: Mapping[str, Any]) -> str:
        value = str(item.get("link") or item.get("share_url") or "")
        try:
            parsed = urlparse(value)
        except ValueError:
            return ""
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https":
            return ""
        if hostname != "douyin.com" and not hostname.endswith(".douyin.com"):
            return ""
        return value
