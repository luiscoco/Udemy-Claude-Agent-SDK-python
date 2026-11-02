"""Lesson 4: Permissions.

Approve, deny or redirect fixture file operations through a host permission callback.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(4)))
