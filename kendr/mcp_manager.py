"""MCP Server Manager — kendr as an MCP client.

Persists a registry of external MCP servers in Kendr's centralized SQLite DB
(``mcp_servers`` table, path resolved via ``KENDR_DB_PATH``) and connects to
them to auto-discover their tools, just like Cursor does.

Supported connection types
--------------------------
* ``http``  – server reachable via HTTP/SSE (e.g. ``http://localhost:8000/mcp``)
* ``stdio`` – server launched via a shell command (e.g. ``python my_server.py``)
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import shlex
import shutil
import sys
import time
import uuid
from typing import Any

_log = logging.getLogger("kendr.mcp_manager")

BROWSER_USE_SERVER_ID = "browser-use-mcp"
BROWSER_USE_SERVER_NAME = "browser-use"


def _is_browser_use_server(server: dict) -> bool:
    server_id = str(server.get("id", "") or "").strip().lower()
    server_name = str(server.get("name", "") or "").strip().lower()
    return server_id == BROWSER_USE_SERVER_ID or server_name == BROWSER_USE_SERVER_NAME


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _resolve_stdio_parts(server: dict, connection: str) -> list[str]:
    try:
        parts = shlex.split(connection)
    except Exception:
        parts = connection.split()
    if not parts:
        parts = [connection]

    if not _is_browser_use_server(server):
        return parts

    command = str(parts[0] if parts else "").strip().lower()
    browser_use_available = _module_available("browser_use")
    browser_use_cli_available = _module_available("browser_use.cli")
    browser_use_bin = shutil.which("browser-use")

    # Best path when package is installed in venv: use its console entrypoint.
    if browser_use_bin:
        return [browser_use_bin, "--mcp"]

    # Prefer the current interpreter so packaged builds do not depend on uvx/PATH shims.
    if browser_use_available:
        return [sys.executable, "-m", "browser_use", "--mcp"]
    if browser_use_cli_available:
        return [sys.executable, "-m", "browser_use.cli", "--mcp"]

    # If module is unavailable, keep explicit user command if it can be resolved.
    if command and (shutil.which(command) or (command in {"uvx", "uv"} and shutil.which(command))):
        return parts

    # Force an executable command for clearer errors (ModuleNotFoundError instead of WinError2).
    return [sys.executable, "-m", "browser_use", "--mcp"]


def _browser_use_env() -> dict[str, str]:
    env = dict(os.environ)
    try:
        from kendr.llm_router import get_api_key

        openai_key = str(get_api_key("openai") or "").strip()
        anthropic_key = str(get_api_key("anthropic") or "").strip()
        if openai_key and not str(env.get("OPENAI_API_KEY", "")).strip():
            env["OPENAI_API_KEY"] = openai_key
        if anthropic_key and not str(env.get("ANTHROPIC_API_KEY", "")).strip():
            env["ANTHROPIC_API_KEY"] = anthropic_key
    except Exception:
        pass
    return env


def _build_stdio_transport(server: dict, connection: str):
    from fastmcp.client.transports.stdio import StdioTransport

    parts = _resolve_stdio_parts(server, connection)
    if not _is_browser_use_server(server):
        return StdioTransport(command=parts[0], args=parts[1:])

    env = _browser_use_env()
    # FastMCP versions vary; try env kwargs with graceful fallback.
    for kwargs in (
        {"env": env},
        {"environment": env},
        {},
    ):
        try:
            return StdioTransport(command=parts[0], args=parts[1:], **kwargs)
        except TypeError:
            continue
    return StdioTransport(command=parts[0], args=parts[1:])


def _sync_mcp_capabilities_safe() -> None:
    try:
        from kendr.capability_sync import sync_mcp_capabilities
        sync_mcp_capabilities(workspace_id="default", actor_user_id="system:mcp-manager")
    except Exception as exc:
        _log.warning("MCP capability sync skipped: %s", exc)


# ---------------------------------------------------------------------------
# Public registry API  (delegates to SQLite persistence layer)
# ---------------------------------------------------------------------------

def list_servers() -> list[dict]:
    """Return all registered MCP servers — includes auth_token (internal use)."""
    from kendr.persistence.mcp_store import list_mcp_servers
    servers = list_mcp_servers()
    _sync_mcp_capabilities_safe()
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
    from kendr.persistence.mcp_store import get_mcp_server
    return get_mcp_server(server_id)


def add_server(
    name: str,
    connection: str,
    server_type: str = "http",
    description: str = "",
    auth_token: str = "",
    enabled: bool = True,
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
    entry = add_mcp_server(
        server_id=server_id,
        name=name.strip() or "Unnamed Server",
        connection=connection.strip(),
        server_type=server_type if server_type in ("http", "stdio") else "http",
        description=description.strip(),
        auth_token=auth_token.strip(),
        enabled=enabled,
    )
    _sync_mcp_capabilities_safe()
    return entry


def remove_server(server_id: str) -> bool:
    from kendr.persistence.mcp_store import remove_mcp_server
    ok = remove_mcp_server(server_id)
    _sync_mcp_capabilities_safe()
    return ok


def toggle_server(server_id: str, enabled: bool) -> bool:
    from kendr.persistence.mcp_store import toggle_mcp_server
    ok = toggle_mcp_server(server_id, enabled)
    _sync_mcp_capabilities_safe()
    return ok


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
            # fastmcp 3.x infer_transport only handles .py/.js paths and HTTP URLs.
            # For arbitrary commands (e.g. "scpr mcp") use StdioTransport directly.
            transport = _build_stdio_transport(server, str(connection or ""))
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


def _client_transport_from_server(server: dict) -> tuple[Any, dict[str, Any]]:
    connection = str(server.get("connection", "") or "").strip()
    server_type = str(server.get("type", "http") or "http").strip().lower()
    auth_token = str(server.get("auth_token", "") or "").strip()
    if not connection:
        raise ValueError("MCP server connection is missing.")

    if server_type == "stdio":
        return _build_stdio_transport(server, connection), {}

    client_kwargs = {"headers": {"Authorization": f"Bearer {auth_token}"}} if auth_token else {}
    return connection, client_kwargs


def _normalize_tool_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "content"):
        parts = result.content if isinstance(result.content, list) else [result.content]
        texts: list[str] = []
        payloads: list[Any] = []
        for part in parts:
            text = getattr(part, "text", None)
            if text is not None:
                texts.append(str(text))
                continue
            payloads.append(part)
            texts.append(str(part))
        return {
            "text": "\n".join(item for item in texts if str(item).strip()).strip(),
            "content": payloads if payloads else parts,
            "raw": result,
        }
    return {"text": str(result), "content": result, "raw": result}


async def _async_call_tool(server: dict, tool_name: str, arguments: dict[str, Any] | None = None, *, timeout: float = 30.0) -> dict[str, Any]:
    try:
        from fastmcp import Client
    except ImportError as exc:
        raise RuntimeError("fastmcp is not installed") from exc

    transport, client_kwargs = _client_transport_from_server(server)
    async with Client(transport, timeout=timeout, **client_kwargs) as client:
        result = await client.call_tool(str(tool_name or "").strip(), dict(arguments or {}))
    normalized = _normalize_tool_result(result)
    normalized["server_id"] = str(server.get("id") or server.get("server_id") or "").strip()
    normalized["server_name"] = str(server.get("name") or "").strip()
    normalized["tool_name"] = str(tool_name or "").strip()
    return normalized


def call_tool(server_id: str, tool_name: str, arguments: dict[str, Any] | None = None, *, timeout: float = 30.0) -> dict[str, Any]:
    server = get_server(server_id)
    if server is None:
        raise ValueError(f"MCP server not found: {server_id}")
    if not bool(server.get("enabled", True)):
        raise ValueError(f"MCP server is disabled: {server_id}")
    return asyncio.run(_async_call_tool(server, tool_name, arguments, timeout=timeout))


def find_server_by_name(name: str, *, enabled_only: bool = True) -> dict | None:
    target = str(name or "").strip().lower()
    if not target:
        return None
    for server in list_servers():
        server_name = str(server.get("name") or "").strip().lower()
        if enabled_only and not bool(server.get("enabled", True)):
            continue
        if server_name == target:
            return server
    return None


def browser_use_server(*, enabled_only: bool = True) -> dict | None:
    for server in list_servers():
        server_id = str(server.get("id") or server.get("server_id") or "").strip()
        server_name = str(server.get("name") or "").strip().lower()
        if server_id != BROWSER_USE_SERVER_ID and server_name != BROWSER_USE_SERVER_NAME:
            continue
        if enabled_only and not bool(server.get("enabled", True)):
            return None
        return server
    return None


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

    result = {
        "ok": error is None,
        "error": error,
        "tools": tools,
        "tool_count": len(tools),
        "last_discovered": now,
        "server_id": server_id,
    }
    _sync_mcp_capabilities_safe()
    return result


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
    mcp.run(transport="sse", host=host, port=port)
'''
