#!/usr/bin/env python3
from __future__ import annotations

import http.client
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Protocol

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CLASH_CONTROLLER = Path("/tmp/verge/verge-mihomo.sock")
PUBLIC_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def log(message: str) -> None:
    print(f"[mobile] {message}", flush=True)


class ClashControllerLike(Protocol):
    def config(self) -> dict: ...

    def global_proxy(self) -> dict: ...

    def select_global(self, name: str) -> None: ...


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float = 3.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.socket_path))


class ClashController:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        connection = UnixHTTPConnection(self.socket_path)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
        finally:
            connection.close()
        if response.status >= 400:
            raise RuntimeError(f"Clash 控制器返回 HTTP {response.status}")
        return json.loads(data) if data else {}

    def config(self) -> dict:
        return self._request("GET", "/configs")

    def global_proxy(self) -> dict:
        return self._request("GET", "/proxies/GLOBAL")

    def select_global(self, name: str) -> None:
        self._request("PUT", "/proxies/GLOBAL", {"name": name})


def prepare_clash_direct(controller: ClashControllerLike) -> str | None:
    if controller.config().get("mode") != "global":
        return None
    proxy = controller.global_proxy()
    previous = str(proxy.get("now", ""))
    choices = {str(item) for item in proxy.get("all", [])}
    if not previous or previous == "DIRECT" or "DIRECT" not in choices:
        return None
    controller.select_global("DIRECT")
    return previous


def restore_clash_proxy(controller: ClashControllerLike, previous: str | None) -> None:
    if previous:
        controller.select_global(previous)


def http_get(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "BeatDance-Mobile-Check/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode(errors="replace")


def local_health_available(origin: str) -> bool:
    try:
        status, body = http_get(f"{origin}/api/v1/health", timeout=1.5)
    except (OSError, urllib.error.URLError):
        return False
    return status == 200 and '"status":"ok"' in body


def wait_for_local_health(origin: str, process: subprocess.Popen[str] | None) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            status, body = http_get(f"{origin}/api/v1/health", timeout=2)
            if status == 200 and '"status":"ok"' in body:
                return
        except (OSError, urllib.error.URLError):
            pass
        if process is not None and process.poll() is not None:
            raise RuntimeError("后端进程提前退出，请检查上方日志。")
        time.sleep(0.25)
    raise RuntimeError(f"后端健康检查超时：{origin}/api/v1/health")


def start_backend(origin: str, port: int) -> subprocess.Popen[str] | None:
    if local_health_available(origin):
        log(f"检测到 {origin} 已有可用后端，将直接复用。")
        return None

    log(f"正在启动后端：{origin}")
    (PROJECT_DIR / "data").mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "DATA_DIR": str(PROJECT_DIR / "data"),
            "H5_DIR": str(PROJECT_DIR / "h5"),
            "FEED_DIR": str(PROJECT_DIR / "data" / "feeds"),
            "SEED_FEED_DIR": str(PROJECT_DIR / "assets" / "samples" / "open_sources"),
            "SEED_REFERENCE_DIR": str(PROJECT_DIR / "assets" / "references"),
            "TUTORIAL_ASSETS_DIR": str(PROJECT_DIR / "assets" / "tutorials"),
            "ALLOW_INSECURE_ADMIN_TOKEN": "true",
            "PUBLIC_BASE_URL": origin,
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_DIR,
        env=environment,
        text=True,
        start_new_session=True,
    )
    wait_for_local_health(origin, process)
    log("后端健康检查通过。")
    return process


def stream_process(process: subprocess.Popen[str], events: queue.Queue[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        events.put(line)


def wait_for_tunnel(
    process: subprocess.Popen[str], events: queue.Queue[str], *, timeout: float = 45
) -> str:
    public_url: str | None = None
    recent_errors: deque[str] = deque(maxlen=8)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = events.get(timeout=0.5)
        except queue.Empty:
            if process.poll() is not None:
                raise RuntimeError("cloudflared 在 Tunnel 注册前退出。")
            continue
        match = PUBLIC_URL_PATTERN.search(line)
        if match:
            public_url = match.group(0)
        if "Registered tunnel connection" in line and public_url:
            return public_url
        if "ERR" in line or "Failed" in line or "Unable" in line:
            recent_errors.append(line.strip())
    detail = "；".join(recent_errors) or "未收到注册成功日志"
    raise RuntimeError(f"Cloudflare Tunnel 注册超时：{detail}")


def wait_for_public_app(public_url: str) -> None:
    deadline = time.monotonic() + 30
    last_error = ""
    while time.monotonic() < deadline:
        try:
            status, body = http_get(f"{public_url}/api/v1/health", timeout=5)
            if status == 200 and '"status":"ok"' in body:
                break
            last_error = f"HTTP {status}: {body[:160]}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(1)
    else:
        raise RuntimeError(f"公网健康检查失败：{last_error}")

    status, page = http_get(f"{public_url}/app/", timeout=10)
    if status != 200 or "BeatDance" not in page:
        raise RuntimeError("公网 H5 页面校验失败。")


def terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    if not shutil.which("cloudflared"):
        raise RuntimeError("未找到 cloudflared，请先执行：brew install cloudflared")

    port = int(os.environ.get("PORT", "8000"))
    origin = f"http://127.0.0.1:{port}"
    backend: subprocess.Popen[str] | None = None
    tunnel: subprocess.Popen[str] | None = None
    controller: ClashController | None = None
    previous_proxy: str | None = None
    proxy_restored = True

    try:
        backend = start_backend(origin, port)

        workaround = os.environ.get("MOBILE_CLASH_DIRECT", "auto").lower()
        controller_path = Path(os.environ.get("CLASH_CONTROLLER", DEFAULT_CLASH_CONTROLLER))
        if workaround != "never" and controller_path.exists():
            controller = ClashController(controller_path)
            try:
                previous_proxy = prepare_clash_direct(controller)
                proxy_restored = previous_proxy is None
                if previous_proxy:
                    log("检测到 Clash 全局代理；Tunnel 注册期间临时切换为 DIRECT。")
            except (OSError, RuntimeError, ValueError) as exc:
                log(f"未启用 Clash 自动兼容：{exc}")
                controller = None
                previous_proxy = None
                proxy_restored = True

        log("正在创建 Cloudflare HTTPS Tunnel…")
        tunnel = subprocess.Popen(
            [
                "cloudflared",
                "tunnel",
                "--protocol",
                "http2",
                "--url",
                origin,
                "--no-autoupdate",
            ],
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        events: queue.Queue[str] = queue.Queue()
        threading.Thread(target=stream_process, args=(tunnel, events), daemon=True).start()
        public_url = wait_for_tunnel(tunnel, events)

        if controller and previous_proxy:
            restore_clash_proxy(controller, previous_proxy)
            proxy_restored = True
            log("Tunnel 已注册，Clash 已恢复到原代理节点。")

        wait_for_public_app(public_url)
        log("公网 API 与 H5 页面检查通过。")
        log(f"手机访问地址：{public_url}/app/")
        log("按 Ctrl+C 关闭隧道，并停止本命令启动的后端。")
        return_code = tunnel.wait()
        if return_code not in (0, -15):
            raise RuntimeError(f"cloudflared 异常退出：{return_code}")
        return 0
    except KeyboardInterrupt:
        log("正在关闭手机体验服务…")
        return 0
    finally:
        if controller and previous_proxy and not proxy_restored:
            try:
                restore_clash_proxy(controller, previous_proxy)
                log("Clash 已恢复到原代理节点。")
            except (OSError, RuntimeError, ValueError) as exc:
                log(f"警告：Clash 自动恢复失败，请手动切回“{previous_proxy}”：{exc}")
        terminate_process(tunnel)
        if backend is not None:
            log("正在停止本次启动的后端服务…")
        terminate_process(backend)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"[mobile] 错误：{exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
