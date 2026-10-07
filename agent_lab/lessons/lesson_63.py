"""Lesson 63: A safe database agent.

Use parameterized SQLite reads and validate versioned write proposals before approval.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(63)))
