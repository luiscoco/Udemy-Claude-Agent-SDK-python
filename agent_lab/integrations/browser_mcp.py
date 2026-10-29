"""Python Playwright MCP server restricted to a configured teaching origin."""

import asyncio
import os
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlparse

from mcp.server.fastmcp import Context, FastMCP


@asynccontextmanager
async def lifespan(server: FastMCP):
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = None
        # Playwright's own Chromium first, then an installed Edge or Chrome.
        for channel in (None, "msedge", "chrome"):
            try:
                browser = await playwright.chromium.launch(channel=channel)
                break
            except Exception:
                continue
        if browser is None:
            raise RuntimeError(
                "No browser is available. Run `uv run playwright install chromium`."
            )
        try:
            yield {"browser": browser, "lock": asyncio.Lock()}
        finally:
            await browser.close()


MAX_REDIRECTS = 5
mcp = FastMCP("python-browser", lifespan=lifespan)


def teaching_origin() -> str:
    return os.getenv("LAB_BROWSER_ORIGIN", "http://127.0.0.1:8080")


def same_origin(url: str, origin: str) -> bool:
    """Scheme, host and port must all match: a lookalike host or other port is refused."""
    target, allowed = urlparse(url), urlparse(origin)
    return (target.scheme, target.hostname, target.port) == (
        allowed.scheme,
        allowed.hostname,
        allowed.port,
    )


@mcp.tool()
async def inspect_page(url: str, ctx: Context) -> dict:
    """Read a page's title and text at the configured LAB_BROWSER_ORIGIN only."""
    from playwright.async_api import Error as PlaywrightError

    origin = teaching_origin()
    if not same_origin(url, origin):
        raise ValueError("URL is outside the configured teaching origin.")
    state = ctx.request_context.lifespan_context
    async with state["lock"]:
        page = await state["browser"].new_page()
        try:
            # Block all off-origin requests, including subresources. The browser follows a
            # redirect without routing the next hop, so never hand it one: follow the chain
            # here, checking every hop, and fulfill only the final response.
            async def route(request):
                current = request.request.url
                for _ in range(MAX_REDIRECTS + 1):
                    if not same_origin(current, origin):
                        break
                    response = await request.fetch(url=current, max_redirects=0)
                    if not 300 <= response.status < 400:
                        await request.fulfill(response=response)
                        return
                    current = urljoin(current, response.headers.get("location", ""))
                await request.abort()

            await page.route("**/*", route)
            try:
                await page.goto(url, timeout=15000)
            except PlaywrightError as exc:
                raise ValueError(
                    "The page could not be loaded within the teaching origin: it failed, or it "
                    f"redirects elsewhere or more than {MAX_REDIRECTS} times."
                ) from exc
            if not same_origin(page.url, origin):  # second guard: never return another site
                raise ValueError("The page left the configured teaching origin.")
            return {
                "title": await page.title(),
                "text": (await page.locator("body").inner_text())[:10000],
                "source_url": page.url,
            }
        finally:
            await page.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
