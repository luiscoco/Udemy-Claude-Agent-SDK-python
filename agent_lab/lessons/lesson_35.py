"""Lesson 35: Session stores.

Persist and reload a host-owned JSON transcript with an atomic replacement.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(35)))
