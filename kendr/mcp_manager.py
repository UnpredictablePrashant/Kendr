"""MCP Server Manager — kendr as an MCP client.

Persists a registry of external MCP servers and connects to them to
auto-discover their tools, just like Cursor does.

Supported connection types
--------------------------
* ``http``  – server reachable via HTTP/SSE (e.g. ``http://localhost:8000/mcp``)
* ``stdio`` – server launched via a shell command (e.g. ``python my_server.py``)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from typing import Any

_log = logging.getLogger("kendr.mcp_manager")

_DEFAULT_STORE = os.path.join(os.path.expanduser("~"), ".kendr", "mcp_registry.json")
_MCP_STORE_PATH = os.getenv("KENDR_MCP_REGISTRY", _DEFAULT_STORE)
_store_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_registry() -> dict:
    try:
        os.makedirs(os.path.dirname(_MCP_STORE_PATH), exist_ok=True)
        if os.path.isfile(_MCP_STORE_PATH):
            with open(_MCP_STORE_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh)
    except Exception as exc:
        _log.warning("Could not load MCP registry: %s", exc)
    return {"servers": {}}


def _save_registry(reg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_MCP_STORE_PATH), exist_ok=True)
        with open(_MCP_STORE_PATH, "w", encoding="utf-8") as fh:
            json.dump(reg, fh, indent=2)
    except Exception as exc:
        _log.warning("Could not save MCP registry: %s", exc)


# ---------------------------------------------------------------------------
# Public registry API
# ---------------------------------------------------------------------------

def list_servers() -> list[dict]:
    """Return all registered MCP servers (sorted by name) — includes auth_token (internal use)."""
    with _store_lock:
        reg = _load_registry()
    servers = list(reg.get("servers", {}).values())
    servers.sort(key=lambda s: s.get("name", "").lower())
    return servers


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
    with _store_lock:
        reg = _load_registry()
    return reg.get("servers", {}).get(server_id)


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
        connections.  Never stored in plaintext beyond the local registry file.
    """
    server_id = uuid.uuid4().hex[:12]
    entry = {
        "id": server_id,
        "name": name.strip() or "Unnamed Server",
        "type": server_type if server_type in ("http", "stdio") else "http",
        "connection": connection.strip(),
        "description": description.strip(),
        "auth_token": auth_token.strip(),
        "enabled": True,
        "tools": [],
        "tool_count": 0,
        "last_discovered": None,
        "status": "unknown",
        "error": None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _store_lock:
        reg = _load_registry()
        reg.setdefault("servers", {})[server_id] = entry
        _save_registry(reg)
    return entry


def remove_server(server_id: str) -> bool:
    with _store_lock:
        reg = _load_registry()
        if server_id in reg.get("servers", {}):
            del reg["servers"][server_id]
            _save_registry(reg)
            return True
    return False


def toggle_server(server_id: str, enabled: bool) -> bool:
    with _store_lock:
        reg = _load_registry()
        srv = reg.get("servers", {}).get(server_id)
        if srv is None:
            return False
        srv["enabled"] = enabled
        _save_registry(reg)
    return True


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
            # stdio transport: pass the command string directly; auth not applicable
            transport = connection
            client_kwargs: dict = {}
        else:
            # HTTP/SSE transport — pass bearer token if provided
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

    Updates the registry and returns the result dict.
    """
    with _store_lock:
        reg = _load_registry()
        server = reg.get("servers", {}).get(server_id)

    if server is None:
        return {"ok": False, "error": "Server not found", "tools": []}

    # Run async discovery in a fresh event loop
    try:
        tools, error = asyncio.run(_async_discover(server))
    except Exception as exc:
        tools, error = [], str(exc)

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _store_lock:
        reg = _load_registry()
        srv = reg.get("servers", {}).get(server_id)
        if srv is not None:
            srv["tools"] = tools
            srv["tool_count"] = len(tools)
            srv["last_discovered"] = now
            srv["status"] = "error" if error else "connected"
            srv["error"] = error
            _save_registry(reg)

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
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port, path="/mcp")
'''
