from __future__ import annotations

from urllib.parse import urlsplit

import httpx


def build_http_client(timeout: float, api_url: str | None = None) -> httpx.Client:
    """Build a CLI client, bypassing system proxies only for loopback APIs.

    macOS system proxies can otherwise intercept localhost requests even when no
    proxy environment variables are set. Remote APIs still honor required proxy
    configuration.
    """

    hostname = urlsplit(api_url).hostname if api_url else None
    loopback = hostname in {"127.0.0.1", "localhost", "::1"}
    return httpx.Client(timeout=timeout, trust_env=not loopback)
