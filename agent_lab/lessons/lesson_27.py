"""Lesson 27: Background tasks.

Own a background Python task and cancel and await it before cleanup.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(27)))
