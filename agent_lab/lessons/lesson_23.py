"""Lesson 23: Plugins.

Load a host-owned local plugin and verify namespaced command discovery and Skill invocation.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(23)))
