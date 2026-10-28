"""Inspect an explicitly supplied trusted remote MCP endpoint."""

import argparse
import asyncio
import json
from urllib.parse import urlparse

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def inspect_remote(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    ):
        raise ValueError("Use HTTPS or a local HTTP MCP endpoint.")
    async with asyncio.timeout(30):
        async with streamable_http_client(url) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                # JSON mode turns AnyUrl resource URIs into strings the CLI can print.
                return {
                    "server": initialized.serverInfo.model_dump(mode="json"),
                    "tools": [tool.model_dump(mode="json") for tool in tools.tools],
                    "resources": [
                        resource.model_dump(mode="json") for resource in resources.resources
                    ],
                }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(inspect_remote(arguments.url)), indent=2))
