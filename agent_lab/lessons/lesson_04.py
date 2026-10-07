"""Lesson 4: Permissions.

Reject paths outside the workspace and tools outside the host's allowlist.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(4)))
