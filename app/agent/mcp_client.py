"""
Thin HTTP client for the MCP server.
Fetches tool schemas once at startup; routes tool calls to the MCP container.
This keeps tool definitions out of the agent core - add a new tool to the
MCP server and the agent picks it up automatically on next restart.
"""
import time
import httpx
from config import settings


_tool_schemas: list[dict] | None = None


async def get_tool_schemas() -> list[dict]:
    global _tool_schemas
    if _tool_schemas is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.mcp_server_url}/tools", timeout=10)
            resp.raise_for_status()
            _tool_schemas = resp.json()["tools"]
    return _tool_schemas


async def call_tool(tool_name: str, arguments: dict, role: str = "sales_user") -> tuple[dict, float]:
    t0 = time.monotonic()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.mcp_server_url}/tools/call",
            json={"tool_name": tool_name, "arguments": arguments, "role": role},
            timeout=30,
        )
        resp.raise_for_status()
    latency_ms = (time.monotonic() - t0) * 1000
    data = resp.json()
    if "error" in data:
        return {"error": data["error"]}, latency_ms
    return data["result"], latency_ms
