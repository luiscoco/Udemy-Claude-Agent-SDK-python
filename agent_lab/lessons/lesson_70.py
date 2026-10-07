"""Lesson 70: The Python SDK.

Use native Python SDK imports directly in the lesson service.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(70)))
