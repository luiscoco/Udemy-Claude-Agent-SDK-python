"""Lesson 16: Settings and environment.

Make settings opt-in and isolate the CLI configuration for each teaching run.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(16)))
