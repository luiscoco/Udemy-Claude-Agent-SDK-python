import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_real_python_stdio_mcp_server_lists_resources_and_executes_tools():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "agent_lab.integrations.notes_mcp"]
    )
    async with asyncio.timeout(20):
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == ["read_note"]
                result = await session.call_tool("read_note", {"name": "welcome"})
                assert not result.isError
                assert "Python" in result.content[0].text
                invalid = await session.call_tool("read_note", {"name": "missing"})
                assert invalid.isError
                resources = await session.list_resources()
                assert str(resources.resources[0].uri) == "notes://welcome"
