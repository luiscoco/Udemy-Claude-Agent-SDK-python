"""Lesson 28: Errors, retries and recovery.

Retry transient operations within a deadline and avoid blindly repeating writes.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(28)))
