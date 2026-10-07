"""Lesson 1: query().

Consume an asynchronous SDK message iterator and distinguish text from the final result.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(1)))
