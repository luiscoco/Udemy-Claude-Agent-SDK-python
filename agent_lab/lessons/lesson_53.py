"""Lesson 53: Debugging an agent run.

Correlate events by run id and redact secret-like values from diagnostic bundles.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(53)))
