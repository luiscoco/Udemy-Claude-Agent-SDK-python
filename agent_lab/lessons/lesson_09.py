"""Lesson 9: System prompts.

Compare a custom prompt with the claude_code preset and an appended instruction.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(9)))
