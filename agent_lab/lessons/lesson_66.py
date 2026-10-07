"""Lesson 66: Real-time frontends over WebSocket.

Use a typed WebSocket protocol and cancel the run when the connection closes.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(66)))
