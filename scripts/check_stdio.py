"""Offline protocol smoke check using the official MCP stdio client."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    async with asyncio.timeout(20):
        params = StdioServerParameters(command=sys.executable, args=["-m", "busqueda_web_mcp.server"])
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                listing = await session.list_tools()
                assert {tool.name for tool in listing.tools} == {"web_search", "fetch_url"}
                result = await session.call_tool("fetch_url", {"url": "http://localhost"})
                data = json.loads(result.content[0].text)
                assert data["error"] is True
                assert data["text"] == ""
                invalid = await session.call_tool("web_search", {"query": "test", "max_results": 9})
                assert invalid.isError
    print("MCP stdio OK: initialize, list_tools, blocked fetch_url, parameter validation")


if __name__ == "__main__":
    asyncio.run(main())
