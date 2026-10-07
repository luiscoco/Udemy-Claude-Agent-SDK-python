"""Lesson 2: Options.

Validate run options before building ClaudeAgentOptions; distinguish omitted values from defaults.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(2)))
