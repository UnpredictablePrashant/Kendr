import json
import os

from fastmcp import FastMCP

from mcp_servers.security_common import capture_page


mcp = FastMCP("super-agent-screenshot")


@mcp.tool
def capture(url: str, headless: bool = True, filename: str = "") -> dict:
    return capture_page(url, filename or None, headless=headless)


@mcp.tool
def capture_with_actions(url: str, actions_json: str = "[]", headless: bool = True, filename: str = "") -> dict:
    try:
        actions = json.loads(actions_json or "[]")
    except Exception:
        actions = []
    return capture_page(url, filename or None, headless=headless, actions=actions if isinstance(actions, list) else [])


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8005"))
    transport = os.getenv("MCP_TRANSPORT", "http")
    mcp.run(transport=transport, host=host, port=port)
