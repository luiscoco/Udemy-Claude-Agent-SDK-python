"""Python headless SDK-review entry point."""
import asyncio

from agent_lab.integrations.review_ci import main

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
