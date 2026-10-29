"""Lesson 64: the real browser MCP service, driven over stdio with a real browser."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


def serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def sites():
    outside_hits: list[str] = []

    class Outside(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            outside_hits.append(self.path)
            body = b"<title>Outside</title><body>SECRET OUTSIDE TEXT</body>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    outside, outside_url = serve(Outside)

    class Teaching(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            if self.path in ("/redirect", "/hop"):
                self.send_response(302)
                self.send_header("Location", f"{outside_url}/secret")
                self.end_headers()
                return
            if self.path == "/inside":  # a redirect that stays on the teaching origin
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            if self.path == "/chain":  # same origin first, then away
                self.send_response(302)
                self.send_header("Location", "/hop")
                self.end_headers()
                return
            body = (
                "<title>Lesson page</title><body>Teaching text"
                f'<img src="{outside_url}/pixel.png"></body>'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    teaching, teaching_url = serve(Teaching)
    yield teaching_url, outside_url, outside_hits
    teaching.shutdown()
    outside.shutdown()


async def call(origin: str, url: str):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent_lab.integrations.browser_mcp"],
        env=dict(os.environ) | {"LAB_BROWSER_ORIGIN": origin},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        return await session.call_tool("inspect_page", {"url": url})


async def test_browser_service_reads_only_the_teaching_origin(sites):
    teaching_url, outside_url, outside_hits = sites
    result = await call(teaching_url, teaching_url + "/")
    if result.isError and "Executable doesn't exist" in result.content[0].text:
        pytest.skip("Playwright's Chromium is not installed: uv run playwright install chromium")
    assert not result.isError, result.content
    page = json.loads(result.content[0].text)
    assert page["title"] == "Lesson page" and "Teaching text" in page["text"]
    assert outside_hits == []  # the off-origin image was blocked, not fetched
    inside = await call(teaching_url, teaching_url + "/inside")
    assert json.loads(inside.content[0].text)["title"] == "Lesson page"

    refused = await call(teaching_url, outside_url + "/secret")
    assert refused.isError and "outside the configured teaching origin" in refused.content[0].text

    # A same-origin URL that redirects away, directly or after a same-origin hop, must not
    # return the other site's content, and the other site must never be contacted.
    for path in ("/redirect", "/chain"):
        redirected = await call(teaching_url, teaching_url + path)
        assert redirected.isError, (path, redirected.content)
        assert "SECRET OUTSIDE TEXT" not in redirected.content[0].text
        assert "redirects elsewhere" in redirected.content[0].text
    assert outside_hits == []
