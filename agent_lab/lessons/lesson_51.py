"""Lesson 51: Unit testing agents without the API.

Use a fake async message source to test host logic without pretending a model ran.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(51)))
