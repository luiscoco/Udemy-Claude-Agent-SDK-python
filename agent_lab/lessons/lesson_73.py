"""Lesson 73: An autonomous PR reviewer and fixer.

Validate findings against changed lines and apply only approved, in-scope patches.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(73)))
