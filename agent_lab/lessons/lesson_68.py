"""Lesson 68: Scheduled and event-driven agents.

Deduplicate trigger ids and await owned scheduled tasks during shutdown.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(68)))
