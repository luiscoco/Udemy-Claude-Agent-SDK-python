"""Lesson 69: Embedding the SDK in a Python desktop app.

Reuse the Python lesson service from NiceGUI native mode.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(69)))
