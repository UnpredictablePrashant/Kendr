"""Capability synchronization helpers.

Phase 1: sync current MCP registry state into unified capability records.
"""

from __future__ import annotations

import re
from typing import Any

from kendr.capability_registry import CapabilityRegistryService
from kendr.persistence import (
    get_capability_by_key,
    list_capabilities,
    list_mcp_servers,
)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return cleaned or "tool"


def _server_health(server_status: str, enabled: bool) -> str:
    status = str(server_status or "").strip().lower()
    if not enabled:
        return "disabled"
    if status in {"connected", "ok", "healthy"}:
        return "healthy"
    if status in {"error", "failed", "unhealthy"}:
        return "error"
    return "unknown"


def sync_mcp_capabilities(
    *,
    workspace_id: str = "default",
    actor_user_id: str = "system:mcp-sync",
    db_path: str = "",
) -> dict:
    service = CapabilityRegistryService(db_path=db_path)
    servers = list_mcp_servers(db_path=db_path)
    seen_keys: set[str] = set()
    counters = {
        "servers_total": len(servers),
        "servers_synced": 0,
        "tools_synced": 0,
        "stale_disabled": 0,
    }

    for server in servers:
        server_id = str(server.get("id", "")).strip()
        if not server_id:
            continue
        enabled = bool(server.get("enabled", True))
        status = "active" if enabled else "disabled"
        server_key = f"mcp.server.{server_id}"
        seen_keys.add(server_key)
        server_metadata = {
            "managed_by": "mcp_sync",
            "managed_type": "mcp_server",
            "mcp_server_id": server_id,
            "mcp_server_name": str(server.get("name", "")).strip(),
            "connection": str(server.get("connection", "")).strip(),
            "transport": str(server.get("type", "http")).strip(),
            "tool_count": int(server.get("tool_count", 0) or 0),
            "server_status": str(server.get("status", "unknown")).strip(),
            "server_error": str(server.get("error", "")).strip(),
            "last_discovered": str(server.get("last_discovered", "")).strip(),
        }
        server_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        existing_server = get_capability_by_key(
            workspace_id=workspace_id,
            key=server_key,
            db_path=db_path,
        )
        if existing_server:
            server_cap = service.update(
                existing_server["id"],
                actor_user_id=actor_user_id,
                workspace_id=workspace_id,
                name=str(server.get("name", "MCP Server")).strip() or "MCP Server",
                description=str(server.get("description", "")).strip() or "MCP server capability.",
                status=status,
                tags=["mcp", "server"],
                metadata=server_metadata,
                schema_in=server_schema,
                schema_out=server_schema,
            ) or existing_server
        else:
            server_cap = service.create(
                workspace_id=workspace_id,
                capability_type="mcp_server",
                key=server_key,
                name=str(server.get("name", "MCP Server")).strip() or "MCP Server",
                description=str(server.get("description", "")).strip() or "MCP server capability.",
                owner_user_id=actor_user_id,
                status=status,
                tags=["mcp", "server"],
                metadata=server_metadata,
                schema_in=server_schema,
                schema_out=server_schema,
            )
        service.record_health(
            server_cap["id"],
            workspace_id=workspace_id,
            status=_server_health(str(server.get("status", "unknown")), enabled),
            error=str(server.get("error", "")).strip(),
        )
        counters["servers_synced"] += 1

        tools = server.get("tools", []) if isinstance(server.get("tools", []), list) else []
        for tool in tools:
            tool_name = str(tool.get("name", "")).strip()
            if not tool_name:
                continue
            tool_key = f"mcp.tool.{server_id}.{_slug(tool_name)}"
            seen_keys.add(tool_key)
            tool_metadata = {
                "managed_by": "mcp_sync",
                "managed_type": "mcp_tool",
                "mcp_server_id": server_id,
                "mcp_server_name": str(server.get("name", "")).strip(),
                "tool_name": tool_name,
            }
            tool_schema = tool.get("schema", {}) if isinstance(tool.get("schema", {}), dict) else {}
            existing_tool = get_capability_by_key(
                workspace_id=workspace_id,
                key=tool_key,
                db_path=db_path,
            )
            if existing_tool:
                tool_cap = service.update(
                    existing_tool["id"],
                    actor_user_id=actor_user_id,
                    workspace_id=workspace_id,
                    name=tool_name,
                    description=str(tool.get("description", "")).strip() or f"MCP tool from {server.get('name', 'server')}.",
                    status=status,
                    tags=["mcp", "tool"],
                    metadata=tool_metadata,
                    schema_in=tool_schema,
                    schema_out={"type": "object"},
                ) or existing_tool
            else:
                tool_cap = service.create(
                    workspace_id=workspace_id,
                    capability_type="tool",
                    key=tool_key,
                    name=tool_name,
                    description=str(tool.get("description", "")).strip() or f"MCP tool from {server.get('name', 'server')}.",
                    owner_user_id=actor_user_id,
                    status=status,
                    tags=["mcp", "tool"],
                    metadata=tool_metadata,
                    schema_in=tool_schema,
                    schema_out={"type": "object"},
                )
            service.link(
                workspace_id=workspace_id,
                parent_capability_id=server_cap["id"],
                child_capability_id=tool_cap["id"],
                relation_type="exposes_tool",
                actor_user_id=actor_user_id,
            )
            counters["tools_synced"] += 1

    managed = []
    for cap_type in ("mcp_server", "tool"):
        managed.extend(
            list_capabilities(
                workspace_id=workspace_id,
                capability_type=cap_type,
                limit=5000,
                db_path=db_path,
            )
        )
    for item in managed:
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
        if metadata.get("managed_by") != "mcp_sync":
            continue
        key = str(item.get("key", "")).strip()
        if key and key not in seen_keys and str(item.get("status", "")).strip().lower() != "disabled":
            service.update(
                item["id"],
                actor_user_id=actor_user_id,
                workspace_id=workspace_id,
                status="disabled",
            )
            counters["stale_disabled"] += 1

    return {
        "workspace_id": workspace_id,
        **counters,
    }

