import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from http_client import build_http_client


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass


def test_script_client_bypasses_system_proxy(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    monkeypatch.delenv("NO_PROXY", raising=False)

    try:
        with build_http_client(timeout=2, api_url=f"http://127.0.0.1:{server.server_port}") as client:
            response = client.get(f"http://127.0.0.1:{server.server_port}/health")
        assert response.status_code == 200
        assert response.text == "ok"
    finally:
        server.shutdown()
        thread.join()
