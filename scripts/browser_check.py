"""Verify the actual NiceGUI browser UI against a running local application."""

import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright


async def main(base_url: str = "http://127.0.0.1:8097", all_lessons: bool = False) -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.goto(f"{base_url}/?lesson=1")
            if "Live mode is disabled" in await page.locator("body").inner_text():
                assert (
                    await page.get_by_role("button", name="Live Agent SDK", exact=True).count() == 0
                )
            await page.get_by_role("button", name="Run exercise", exact=True).click()
            await page.get_by_text("Completed", exact=True).first.wait_for()
            await page.get_by_text("LOCAL PYTHON RESULT", exact=True).wait_for()
            assert not await page.get_by_text(re.compile(r"^STARTED\s+\{")).is_visible()
            assert (
                "Enable LAB_ENABLE_LIVE=true before making paid SDK calls"
                not in await page.locator("body").inner_text()
            )
            await page.goto(f"{base_url}/?lesson=5")
            await page.get_by_role("button", name="Run exercise", exact=True).click()
            await page.get_by_text("Completed", exact=True).first.wait_for()
            assert "42.0" in await page.locator("body").inner_text()
            await page.get_by_role("tab", name="Learn", exact=True).click()
            await page.get_by_role("heading", name="Lesson 5: Custom tools", exact=True).wait_for()
            await page.get_by_role("tab", name="Python source", exact=True).click()
            assert "Calculation" in await page.locator("body").inner_text()
            for number, title in (
                (41, "Interactive Python client lifecycle"),
                (69, "Embedding the SDK in a Python desktop app"),
            ):
                await page.goto(f"{base_url}/?lesson={number}")
                await page.get_by_role("tab", name="Learn", exact=True).click()
                await page.get_by_role(
                    "heading", name=f"Lesson {number}: {title}", exact=True
                ).wait_for()
            await page.goto(f"{base_url}/?lesson=75")
            await page.get_by_role("button", name="Run exercise", exact=True).click()
            await page.get_by_text("Completed", exact=True).first.wait_for()
            assert "3 acceptance checks passed" in await page.locator("body").inner_text()
            checked = [1, 5, 41, 69, 75]
            if all_lessons:
                for number in range(1, 76):
                    await page.goto(f"{base_url}/?lesson={number}")
                    await page.get_by_role("button", name="Run exercise", exact=True).click()
                    await page.get_by_text("Completed", exact=True).first.wait_for()
                    await page.get_by_text("LOCAL PYTHON RESULT", exact=True).wait_for()
                    assert not await page.get_by_text(re.compile(r"^STARTED\s+\{")).is_visible()
                    assert not await page.get_by_text("Could not start", exact=True).count()
                    if number == 72:
                        link = page.get_by_role("link", name="Download incident report (.docx)")
                        response = await page.request.get(base_url + (await link.get_attribute("href")))
                        assert response.ok and (await response.body()).startswith(b"PK")
                    print(f"Lesson {number}: formatted output OK", flush=True)
                checked = list(range(1, 76))
            folder = Path(".lab-data")
            await asyncio.to_thread(folder.mkdir, exist_ok=True)
            await page.screenshot(path=str(folder / "python-lab-desktop.png"), full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.goto(f"{base_url}/?lesson=1")
            await page.get_by_role("button", name="Run exercise", exact=True).wait_for()
            overflow = await page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth"
            )
            await page.screenshot(path=str(folder / "python-lab-mobile.png"), full_page=True)
            assert not overflow, "Mobile layout overflows horizontally"
            assert not errors, errors
            print(
                json.dumps(
                    {
                        "browser": "Edge headless",
                        "lessons": checked,
                        "javascript_errors": errors,
                        "mobile_overflow": overflow,
                    }
                )
            )
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8097")
    parser.add_argument("--all-lessons", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.base_url.rstrip("/"), args.all_lessons))
