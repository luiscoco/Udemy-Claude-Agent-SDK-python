"""Lesson 67: Multi-tenant SaaS architecture.

Capture tenant identity in host state and reject cross-tenant access.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(67)))
