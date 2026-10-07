"""Lesson 49: Deployment and headless CI.

Run a Python CLI exercise with a meaningful exit code and test it without API access.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(49)))
