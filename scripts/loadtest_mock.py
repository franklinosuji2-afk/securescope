"""A tiny local web site for the load tests to scan: one fixed address, no internet, nothing real.

python scripts/loadtest_mock.py            # listens on 127.0.0.1:8765
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765


class Handler(BaseHTTPRequestHandler):
    server_version = "mock"
    sys_version = ""

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        body = b"<html><title>load test target</title></html>"
        self.send_response(200 if self.path.split("?")[0] == "/plain" else 404)
        self.send_header("Content-Type", "text/html")
        self.send_header("Server", "nginx/1.18.0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    print(f"Mock target on http://127.0.0.1:{PORT}/plain (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
