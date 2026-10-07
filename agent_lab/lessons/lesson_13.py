"""Lesson 13: MCP servers.

Expose typed tools over the official MCP Python SDK's stdio transport.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(13)))
