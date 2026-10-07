"""Lesson 61: Exposing an agent as an MCP server.

Expose a typed Python MCP tool whose async handler invokes the official Agent SDK.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(61)))
