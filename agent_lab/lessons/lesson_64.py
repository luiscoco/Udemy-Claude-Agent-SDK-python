"""Lesson 64: Browser automation with Playwright MCP.

Use an explicit external MCP browser service rather than exposing a host shell.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(64)))
