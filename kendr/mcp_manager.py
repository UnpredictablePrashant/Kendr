"""MCP Server Manager — kendr as an MCP client.

Persists a registry of external MCP servers in the local SQLite DB
(``output/agent_workflow.sqlite3``, table ``mcp_servers``) and connects to
them to auto-discover their tools, just like Cursor does.

Supported connection types
--------------------------
* ``http``  – server reachable via HTTP/SSE (e.g. ``http://localhost:8000/mcp``)
* ``stdio`` – server launched via a shell command (e.g. ``python my_server.py``)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

_log = logging.getLogger("kendr.mcp_manager")


# ---------------------------------------------------------------------------
# Public registry API  (delegates to SQLite persistence layer)
# ---------------------------------------------------------------------------

def list_servers() -> list[dict]:
    """Return all registered MCP servers — includes auth_token (internal use)."""
    from kendr.persistence.mcp_store import list_mcp_servers
    return list_mcp_servers()


def list_servers_safe() -> list[dict]:
    """Return all registered MCP servers with auth_token redacted — safe for API responses."""
    servers = list_servers()
    result = []
    for s in servers:
        entry = dict(s)
        if entry.get("auth_token"):
            entry["auth_token"] = "****"
        result.append(entry)
    return result


def get_server(server_id: str) -> dict | None:
    from kendr.persistence.mcp_store import get_mcp_server
    return get_mcp_server(server_id)


def add_server(
    name: str,
    connection: str,
    server_type: str = "http",
    description: str = "",
    auth_token: str = "",
) -> dict:
    """Register a new MCP server.

    Parameters
    ----------
    name:
        Human-readable label (e.g. ``"My Research Server"``).
    connection:
        URL for ``http`` type (``http://host:port/mcp``) or
        shell command for ``stdio`` type (``python my_server.py``).
    server_type:
        ``"http"`` or ``"stdio"``.
    description:
        Optional short description shown in the UI.
    auth_token:
        Optional bearer token sent as ``Authorization: Bearer <token>`` for HTTP
        connections.  Stored in the local DB (localhost-only access).
    """
    from kendr.persistence.mcp_store import add_mcp_server
    server_id = uuid.uuid4().hex[:12]
    return add_mcp_server(
        server_id=server_id,
        name=name.strip() or "Unnamed Server",
        connection=connection.strip(),
        server_type=server_type if server_type in ("http", "stdio") else "http",
        description=description.strip(),
        auth_token=auth_token.strip(),
    )


def remove_server(server_id: str) -> bool:
    from kendr.persistence.mcp_store import remove_mcp_server
    return remove_mcp_server(server_id)


def toggle_server(server_id: str, enabled: bool) -> bool:
    from kendr.persistence.mcp_store import toggle_mcp_server
    return toggle_mcp_server(server_id, enabled)


# ---------------------------------------------------------------------------
# Tool discovery (async core, sync wrapper)
# ---------------------------------------------------------------------------

async def _async_discover(server: dict) -> tuple[list[dict], str | None]:
    """Connect to the MCP server and list its tools.

    Returns ``(tools_list, error_or_None)``.
    """
    try:
        from fastmcp import Client  # local import — fastmcp may not always be needed
    except ImportError:
        return [], "fastmcp is not installed"

    connection = server.get("connection", "")
    server_type = server.get("type", "http")
    auth_token = server.get("auth_token", "")

    try:
        if server_type == "stdio":
            transport = connection
            client_kwargs: dict = {}
        else:
            transport = connection
            if auth_token:
                client_kwargs = {"headers": {"Authorization": f"Bearer {auth_token}"}}
            else:
                client_kwargs = {}

        async with Client(transport, timeout=15, **client_kwargs) as client:
            raw_tools = await client.list_tools()

        tools = []
        for t in raw_tools:
            schema: dict[str, Any] = {}
            if hasattr(t, "inputSchema") and t.inputSchema:
                schema = dict(t.inputSchema) if not isinstance(t.inputSchema, dict) else t.inputSchema
            elif hasattr(t, "input_schema") and t.input_schema:
                schema = dict(t.input_schema) if not isinstance(t.input_schema, dict) else t.input_schema
            tools.append({
                "name": t.name,
                "description": getattr(t, "description", "") or "",
                "schema": schema,
            })
        return tools, None
    except Exception as exc:
        return [], str(exc)


def discover_tools(server_id: str) -> dict:
    """Synchronously discover tools from a registered MCP server.

    Updates the DB and returns the result dict.
    """
    from kendr.persistence.mcp_store import get_mcp_server, update_mcp_server_tools

    server = get_mcp_server(server_id)
    if server is None:
        return {"ok": False, "error": "Server not found", "tools": []}

    try:
        tools, error = asyncio.run(_async_discover(server))
    except Exception as exc:
        tools, error = [], str(exc)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    update_mcp_server_tools(
        server_id=server_id,
        tools=tools,
        status="error" if error else "connected",
        error=error,
        last_discovered=now,
    )

    return {
        "ok": error is None,
        "error": error,
        "tools": tools,
        "tool_count": len(tools),
        "last_discovered": now,
        "server_id": server_id,
    }


# ---------------------------------------------------------------------------
# Scaffolding code snippet
# ---------------------------------------------------------------------------

SCAFFOLD_CODE = '''"""
FastMCP Server Scaffold — drop this into any Python file and run it.

Install:
    pip install fastmcp

Run as HTTP server (SSE transport):
    python my_server.py

Connect from kendr MCP Manager:
    Type: HTTP
    Connection: http://localhost:8000/mcp
"""

from fastmcp import FastMCP

# Create the server — give it a meaningful name
mcp = FastMCP("my-kendr-tool-server")


# ── Tool #1 ─────────────────────────────────────────────────────────────────
@mcp.tool
def echo(message: str) -> str:
    """Return the message back to the caller. Good baseline test tool."""
    return f"Echo: {message}"


# ── Tool #2 ─────────────────────────────────────────────────────────────────
@mcp.tool
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


# ── Tool #3: returning structured data ──────────────────────────────────────
@mcp.tool
def system_info() -> dict:
    """Return basic system information."""
    import platform, os
    return {
        "platform": platform.system(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
    }


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Starts an HTTP server on http://localhost:8000/mcp
    # Change host/port via env: MCP_HOST, MCP_PORT
    import os
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    mcp.run(transport="sse", host=host, port=port)
'''
