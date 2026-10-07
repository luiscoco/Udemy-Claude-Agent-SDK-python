"""Lesson 17: Checkpointing and rewind.

Snapshot a workspace file and restore it; inspect the SDK's rewind interface separately.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(17)))
