"""Lesson 47: Multi-agent orchestration.

Execute a dependency graph in waves with bounded concurrency and failure propagation.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(47)))
