"""SQLite-backed MCP server registry.

All MCP server state is stored in the shared agent_workflow.sqlite3 database
under the `mcp_servers` table.  A one-time migration from the legacy JSON
registry (``~/.kendr/mcp_registry.json``) runs automatically on first use.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from .core import DB_PATH, _connect, initialize_db

_log = logging.getLogger("kendr.persistence.mcp_store")

_LEGACY_JSON = os.path.join(os.path.expanduser("~"), ".kendr", "mcp_registry.json")
_MIGRATED_FLAG = os.path.join(os.path.expanduser("~"), ".kendr", "mcp_migrated.flag")


def _row_to_dict(row) -> dict:
    d = dict(row)
    tools_json = d.pop("tools_json", "[]") or "[]"
    try:
        d["tools"] = json.loads(tools_json)
    except Exception:
        d["tools"] = []
    d["enabled"] = bool(d.get("enabled", 1))
    d["tool_count"] = d.get("tool_count", 0) or 0
    d["id"] = d.pop("server_id")
    return d


def _maybe_migrate(db_path: str = DB_PATH) -> None:
    if os.path.exists(_MIGRATED_FLAG):
        return
    if not os.path.isfile(_LEGACY_JSON):
        try:
            os.makedirs(os.path.dirname(_MIGRATED_FLAG), exist_ok=True)
            open(_MIGRATED_FLAG, "w").close()
        except Exception:
            pass
        return
    try:
        with open(_LEGACY_JSON, "r", encoding="utf-8") as fh:
            legacy = json.load(fh)
        servers = legacy.get("servers", {})
        if servers:
            initialize_db(db_path)
            with _connect(db_path) as conn:
                existing = {
                    r["server_id"]
                    for r in conn.execute("SELECT server_id FROM mcp_servers").fetchall()
                }
                for srv in servers.values():
                    sid = srv.get("id") or srv.get("server_id", "")
                    if not sid or sid in existing:
                        continue
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO mcp_servers
                            (server_id, name, type, connection, description,
                             auth_token, enabled, tools_json, tool_count,
                             status, error, last_discovered, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            sid,
                            srv.get("name", ""),
                            srv.get("type", "http"),
                            srv.get("connection", ""),
                            srv.get("description", ""),
                            srv.get("auth_token", ""),
                            1 if srv.get("enabled", True) else 0,
                            json.dumps(srv.get("tools", [])),
                            srv.get("tool_count", 0),
                            srv.get("status", "unknown"),
                            srv.get("error") or "",
                            srv.get("last_discovered") or "",
                            srv.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
                        ),
                    )
        _log.info("MCP registry migrated from JSON (%d servers)", len(servers))
    except Exception as exc:
        _log.warning("MCP JSON migration failed (non-fatal): %s", exc)
    try:
        os.makedirs(os.path.dirname(_MIGRATED_FLAG), exist_ok=True)
        open(_MIGRATED_FLAG, "w").close()
    except Exception:
        pass


def list_mcp_servers(db_path: str = DB_PATH) -> list[dict]:
    initialize_db(db_path)
    _maybe_migrate(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM mcp_servers ORDER BY LOWER(name)"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_mcp_server(server_id: str, db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    _maybe_migrate(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM mcp_servers WHERE server_id=?", (server_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def add_mcp_server(
    server_id: str,
    name: str,
    connection: str,
    server_type: str = "http",
    description: str = "",
    auth_token: str = "",
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    _maybe_migrate(db_path)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO mcp_servers
                (server_id, name, type, connection, description,
                 auth_token, enabled, tools_json, tool_count,
                 status, error, last_discovered, created_at)
            VALUES (?,?,?,?,?,?,1,'[]',0,'unknown','','',?)
            """,
            (server_id, name, server_type, connection, description, auth_token, now),
        )
    return get_mcp_server(server_id, db_path) or {}


def remove_mcp_server(server_id: str, db_path: str = DB_PATH) -> bool:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        changed = conn.execute(
            "DELETE FROM mcp_servers WHERE server_id=?", (server_id,)
        ).rowcount
    return changed > 0


def toggle_mcp_server(server_id: str, enabled: bool, db_path: str = DB_PATH) -> bool:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        changed = conn.execute(
            "UPDATE mcp_servers SET enabled=? WHERE server_id=?",
            (1 if enabled else 0, server_id),
        ).rowcount
    return changed > 0


def update_mcp_server_tools(
    server_id: str,
    tools: list[dict],
    status: str,
    error: str | None,
    last_discovered: str,
    db_path: str = DB_PATH,
) -> bool:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        changed = conn.execute(
            """
            UPDATE mcp_servers
               SET tools_json=?, tool_count=?, status=?, error=?, last_discovered=?
             WHERE server_id=?
            """,
            (
                json.dumps(tools),
                len(tools),
                status,
                error or "",
                last_discovered,
                server_id,
            ),
        ).rowcount
    return changed > 0
