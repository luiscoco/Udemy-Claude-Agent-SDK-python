"""Python Playwright MCP server restricted to a configured teaching origin."""

import asyncio
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from mcp.server.fastmcp import Context, FastMCP


@asynccontextmanager
async def lifespan(server: FastMCP):
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            yield {"browser": browser, "lock": asyncio.Lock()}
        finally:
            await browser.close()


mcp = FastMCP("python-browser", lifespan=lifespan)


@mcp.tool()
async def inspect_page(url: str, ctx: Context) -> dict:
    """Read a page's title and text at the configured LAB_BROWSER_ORIGIN only."""
    target = urlparse(url)
    origin = urlparse(os.getenv("LAB_BROWSER_ORIGIN", "http://127.0.0.1:8080"))
    if (target.scheme, target.hostname, target.port) != (
        origin.scheme,
        origin.hostname,
        origin.port,
    ):
        raise ValueError("URL is outside the configured teaching origin.")
    state = ctx.request_context.lifespan_context
    async with state["lock"]:
        page = await state["browser"].new_page()
        try:
            # Block all off-origin requests, including redirects and subresources.
            async def route(request):
                parsed = urlparse(request.request.url)
                if (parsed.scheme, parsed.hostname, parsed.port) == (
                    origin.scheme,
                    origin.hostname,
                    origin.port,
                ):
                    await request.continue_()
                else:
                    await request.abort()

            await page.route("**/*", route)
            await page.goto(url, timeout=15000)
            return {
                "title": await page.title(),
                "text": (await page.locator("body").inner_text())[:10000],
                "source_url": page.url,
            }
        finally:
            await page.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
