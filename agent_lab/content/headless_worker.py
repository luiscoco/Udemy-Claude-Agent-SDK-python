"""Owned local Lesson 49 HTTP worker; stdout JSONL is its supervisor receipt."""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, separators=(",", ":")), flush=True)


def main() -> int:
    if len(sys.argv) != 5:
        return 2
    run_id, control, job_ms_text, drain_ms_text = sys.argv[1:]
    job_ms, drain_ms = int(job_ms_text), int(drain_ms_text)
    if job_ms != 1000 or drain_ms != 2000:
        return 2
    lock = threading.Lock()
    state: dict[str, Any] = {"active": False, "draining": False,
                             "release": threading.Event(), "drain_at": None}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            pass

        def answer(self, status: int, value: dict[str, Any]) -> None:
            data = json.dumps(value, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def request_body(self) -> dict[str, Any] | None:
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or self.headers.get("Origin"):
                return None
            raw_length = self.headers.get("Content-Length", "")
            if not raw_length.isdigit() or not 0 <= int(raw_length) <= 1024:
                return None
            try:
                value = json.loads(self.rfile.read(int(raw_length)))
            except (UnicodeDecodeError, ValueError):
                return None
            return value if isinstance(value, dict) else None

        def do_GET(self) -> None:
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or self.headers.get("Origin"):
                self.answer(404, {"error": "not_found"})
            elif self.path == "/health":
                self.answer(200, {"run": run_id, "healthy": True})
            elif self.path == "/ready":
                with lock:
                    draining = state["draining"]
                self.answer(503 if draining else 200, {"run": run_id, "ready": not draining})
            else:
                self.answer(404, {"error": "not_found"})

        def do_POST(self) -> None:
            body = self.request_body()
            if body is None:
                self.answer(400, {"error": "invalid_input"})
                return
            if self.path == "/job":
                if (set(body) != {"run", "job"} or body["run"] != run_id or
                        not isinstance(body["job"], str) or not 1 <= len(body["job"]) <= 48 or
                        not body["job"].isascii() or not body["job"].replace("-", "").isalnum()):
                    self.answer(400, {"error": "invalid_job"})
                    return
                with lock:
                    if state["draining"]:
                        self.answer(503, {"error": "draining"})
                        return
                    if state["active"]:
                        self.answer(429, {"error": "busy"})
                        return
                    state["active"] = True
                emit({"kind": "job-start", "run": run_id, "job": body["job"]})
                until = time.monotonic() + job_ms / 1000
                status = 200
                while not state["release"].wait(0.01):
                    now = time.monotonic()
                    if now >= until:
                        status = 408
                        break
                    with lock:
                        drain_at = state["drain_at"]
                    if drain_at is not None and now >= drain_at + drain_ms / 1000:
                        status = 503
                        break
                with lock:
                    state["active"] = False
                    draining = state["draining"]
                emit({"kind": "job-end", "run": run_id, "job": body["job"], "status": status})
                self.answer(status, {"run": run_id, "job": body["job"], "status": status})
                if draining:
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path in {"/control/drain", "/control/release"} and body == {"run": run_id, "control": control}:
                if self.path == "/control/drain":
                    with lock:
                        state["draining"] = True
                        state["drain_at"] = time.monotonic()
                        active = state["active"]
                    emit({"kind": "draining", "run": run_id})
                    self.answer(200, {"run": run_id, "draining": True})
                    if not active:
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    state["release"].set()
                    self.answer(200, {"run": run_id, "released": True})
                return
            self.answer(404, {"error": "not_found"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    emit({"kind": "listening", "run": run_id, "port": server.server_port,
          "slot": 1, "job_ms": job_ms, "drain_ms": drain_ms})
    try:
        server.serve_forever(poll_interval=0.02)
    finally:
        server.server_close()
    emit({"kind": "closed", "run": run_id})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
