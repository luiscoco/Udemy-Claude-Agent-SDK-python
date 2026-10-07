"""Lesson 57: Parallel workers in Git worktrees.

Create isolated Git worktrees and serialize operations on shared repository state.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(57)))
