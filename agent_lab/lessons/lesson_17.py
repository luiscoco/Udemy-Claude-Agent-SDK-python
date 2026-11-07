"""Lesson 17: Checkpointing and rewind.

Capture a user checkpoint, edit one owned file, and verify native rewind with file hashes.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(17)))
