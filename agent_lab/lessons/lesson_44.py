"""Lesson 44: Observability with OpenTelemetry.

Record a real host span with attributes and export telemetry only when configured.
"""
import asyncio

from agent_lab.cli import run_lesson

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_lesson(44)))
