"""SQLite-backed capability control-plane store (Phase 0).

This module provides typed persistence helpers for unified capability records:
skills, MCP servers, APIs, and agents.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .core import DB_PATH, _connect, initialize_db


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw) if str(raw or "").strip() else default
    except Exception:
        return default


def _capability_row_to_dict(row) -> dict:
    payload = dict(row)
    payload["id"] = payload.pop("capability_id")
    payload["key"] = payload.pop("capability_key")
    payload["tags"] = _json_loads(payload.pop("tags_json", "[]"), [])
    payload["metadata"] = _json_loads(payload.pop("metadata_json", "{}"), {})
    payload["schema_in"] = _json_loads(payload.pop("schema_in_json", "{}"), {})
    payload["schema_out"] = _json_loads(payload.pop("schema_out_json", "{}"), {})
    return payload


def create_capability(
    *,
    workspace_id: str,
    capability_type: str,
    key: str,
    name: str,
    description: str,
    owner_user_id: str,
    visibility: str = "workspace",
    status: str = "draft",
    version: int = 1,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    schema_in: dict | None = None,
    schema_out: dict | None = None,
    auth_profile_id: str = "",
    policy_profile_id: str = "",
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    capability_id = str(uuid.uuid4())
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO capabilities (
                capability_id, workspace_id, type, capability_key, name, description,
                owner_user_id, status, visibility, version, tags_json, metadata_json,
                schema_in_json, schema_out_json, auth_profile_id, policy_profile_id,
                health_status, health_last_checked_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', NULL, ?, ?)
            """,
            (
                capability_id,
                workspace_id,
                capability_type,
                key,
                name,
                description,
                owner_user_id,
                status,
                visibility,
                max(1, int(version)),
                _json_dumps(tags or []),
                _json_dumps(metadata or {}),
                _json_dumps(schema_in or {}),
                _json_dumps(schema_out or {}),
                str(auth_profile_id or "").strip() or None,
                str(policy_profile_id or "").strip() or None,
                now,
                now,
            ),
        )
    return get_capability(capability_id, db_path=db_path) or {}


def get_capability(capability_id: str, *, db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM capabilities WHERE capability_id=?",
            (capability_id,),
        ).fetchone()
    return _capability_row_to_dict(row) if row else None


def get_capability_by_key(
    *,
    workspace_id: str,
    key: str,
    version: int = 1,
    db_path: str = DB_PATH,
) -> dict | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM capabilities
            WHERE workspace_id=? AND capability_key=? AND version=?
            LIMIT 1
            """,
            (workspace_id, key, max(1, int(version))),
        ).fetchone()
    return _capability_row_to_dict(row) if row else None


def list_capabilities(
    *,
    workspace_id: str = "",
    capability_type: str = "",
    status: str = "",
    visibility: str = "",
    search: str = "",
    limit: int = 200,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    where: list[str] = []
    values: list[Any] = []
    if workspace_id:
        where.append("workspace_id=?")
        values.append(workspace_id)
    if capability_type:
        where.append("type=?")
        values.append(capability_type)
    if status:
        where.append("status=?")
        values.append(status)
    if visibility:
        where.append("visibility=?")
        values.append(visibility)
    if search:
        where.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(capability_key) LIKE ?)")
        like = f"%{search.lower()}%"
        values.extend([like, like, like])
    sql = "SELECT * FROM capabilities"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY LOWER(name), version DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(values)).fetchall()
    return [_capability_row_to_dict(row) for row in rows]


def update_capability(
    capability_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    visibility: str | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    schema_in: dict | None = None,
    schema_out: dict | None = None,
    auth_profile_id: str | None = None,
    policy_profile_id: str | None = None,
    db_path: str = DB_PATH,
) -> dict | None:
    initialize_db(db_path)
    updates: list[str] = []
    values: list[Any] = []
    if name is not None:
        updates.append("name=?")
        values.append(name)
    if description is not None:
        updates.append("description=?")
        values.append(description)
    if status is not None:
        updates.append("status=?")
        values.append(status)
    if visibility is not None:
        updates.append("visibility=?")
        values.append(visibility)
    if tags is not None:
        updates.append("tags_json=?")
        values.append(_json_dumps(tags))
    if metadata is not None:
        updates.append("metadata_json=?")
        values.append(_json_dumps(metadata))
    if schema_in is not None:
        updates.append("schema_in_json=?")
        values.append(_json_dumps(schema_in))
    if schema_out is not None:
        updates.append("schema_out_json=?")
        values.append(_json_dumps(schema_out))
    if auth_profile_id is not None:
        updates.append("auth_profile_id=?")
        values.append(str(auth_profile_id).strip() or None)
    if policy_profile_id is not None:
        updates.append("policy_profile_id=?")
        values.append(str(policy_profile_id).strip() or None)
    if not updates:
        return get_capability(capability_id, db_path=db_path)
    updates.append("updated_at=?")
    values.append(_utc_now())
    values.append(capability_id)
    with _connect(db_path) as conn:
        conn.execute(
            f"UPDATE capabilities SET {', '.join(updates)} WHERE capability_id=?",
            tuple(values),
        )
    return get_capability(capability_id, db_path=db_path)


def delete_capability(capability_id: str, *, db_path: str = DB_PATH) -> bool:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "DELETE FROM capability_relations WHERE parent_capability_id=? OR child_capability_id=?",
            (capability_id, capability_id),
        )
        conn.execute(
            "DELETE FROM capability_health_runs WHERE capability_id=?",
            (capability_id,),
        )
        conn.execute(
            "DELETE FROM capability_audit_events WHERE capability_id=?",
            (capability_id,),
        )
        changed = conn.execute(
            "DELETE FROM capabilities WHERE capability_id=?",
            (capability_id,),
        ).rowcount
    return changed > 0


def set_capability_health(
    capability_id: str,
    *,
    workspace_id: str,
    status: str,
    latency_ms: int | None = None,
    error: str = "",
    db_path: str = DB_PATH,
) -> None:
    initialize_db(db_path)
    now = _utc_now()
    health_run_id = str(uuid.uuid4())
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO capability_health_runs (
                health_run_id, workspace_id, capability_id, status, latency_ms, error, checked_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (health_run_id, workspace_id, capability_id, status, latency_ms, error or None, now),
        )
        conn.execute(
            """
            UPDATE capabilities
            SET health_status=?, health_last_checked_at=?, updated_at=?
            WHERE capability_id=?
            """,
            (status, now, now, capability_id),
        )


def create_auth_profile(
    *,
    workspace_id: str,
    auth_type: str,
    provider: str,
    secret_ref: str,
    scopes: list[str] | None = None,
    metadata: dict | None = None,
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    auth_profile_id = str(uuid.uuid4())
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO auth_profiles (
                auth_profile_id, workspace_id, auth_type, provider, secret_ref,
                scopes_json, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                auth_profile_id,
                workspace_id,
                auth_type,
                provider,
                secret_ref,
                _json_dumps(scopes or []),
                _json_dumps(metadata or {}),
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM auth_profiles WHERE auth_profile_id=?",
            (auth_profile_id,),
        ).fetchone()
    payload = dict(row)
    payload["id"] = payload.pop("auth_profile_id")
    payload["scopes"] = _json_loads(payload.pop("scopes_json", "[]"), [])
    payload["metadata"] = _json_loads(payload.pop("metadata_json", "{}"), {})
    return payload


def create_policy_profile(
    *,
    workspace_id: str,
    name: str,
    rules: dict,
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    policy_profile_id = str(uuid.uuid4())
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO policy_profiles (
                policy_profile_id, workspace_id, name, rules_json, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (policy_profile_id, workspace_id, name, _json_dumps(rules or {}), now),
        )
        row = conn.execute(
            "SELECT * FROM policy_profiles WHERE policy_profile_id=?",
            (policy_profile_id,),
        ).fetchone()
    payload = dict(row)
    payload["id"] = payload.pop("policy_profile_id")
    payload["rules"] = _json_loads(payload.pop("rules_json", "{}"), {})
    return payload


def add_capability_relation(
    *,
    workspace_id: str,
    parent_capability_id: str,
    child_capability_id: str,
    relation_type: str,
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        existing = conn.execute(
            """
            SELECT * FROM capability_relations
            WHERE workspace_id=? AND parent_capability_id=? AND child_capability_id=? AND relation_type=?
            LIMIT 1
            """,
            (workspace_id, parent_capability_id, child_capability_id, relation_type),
        ).fetchone()
        if existing:
            payload = dict(existing)
            payload["id"] = payload.pop("relation_id")
            return payload

    relation_id = str(uuid.uuid4())
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO capability_relations (
                relation_id, workspace_id, parent_capability_id, child_capability_id, relation_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (relation_id, workspace_id, parent_capability_id, child_capability_id, relation_type, now),
        )
        row = conn.execute(
            "SELECT * FROM capability_relations WHERE relation_id=?",
            (relation_id,),
        ).fetchone()
    payload = dict(row) if row else {
        "relation_id": relation_id,
        "workspace_id": workspace_id,
        "parent_capability_id": parent_capability_id,
        "child_capability_id": child_capability_id,
        "relation_type": relation_type,
        "created_at": now,
    }
    payload["id"] = payload.pop("relation_id")
    return payload


def insert_capability_audit_event(
    *,
    workspace_id: str,
    actor_user_id: str,
    action: str,
    payload: dict | None = None,
    capability_id: str = "",
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    audit_event_id = str(uuid.uuid4())
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO capability_audit_events (
                audit_event_id, workspace_id, capability_id, actor_user_id, action, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_event_id,
                workspace_id,
                str(capability_id or "").strip() or None,
                actor_user_id,
                action,
                _json_dumps(payload or {}),
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM capability_audit_events WHERE audit_event_id=?",
            (audit_event_id,),
        ).fetchone()
    event = dict(row)
    event["id"] = event.pop("audit_event_id")
    event["payload"] = _json_loads(event.pop("payload_json", "{}"), {})
    return event


def list_capability_health_runs(
    *,
    workspace_id: str,
    capability_id: str = "",
    limit: int = 50,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    where: list[str] = ["workspace_id=?"]
    values: list[Any] = [workspace_id]
    if capability_id:
        where.append("capability_id=?")
        values.append(capability_id)
    sql = "SELECT * FROM capability_health_runs WHERE " + " AND ".join(where)
    sql += " ORDER BY checked_at DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(values)).fetchall()
    return [dict(row) for row in rows]


def list_capability_audit_events(
    *,
    workspace_id: str,
    capability_id: str = "",
    action: str = "",
    limit: int = 100,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    where: list[str] = ["workspace_id=?"]
    values: list[Any] = [workspace_id]
    if capability_id:
        where.append("capability_id=?")
        values.append(capability_id)
    if action:
        where.append("action=?")
        values.append(action)
    sql = "SELECT * FROM capability_audit_events WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(values)).fetchall()
    events: list[dict] = []
    for row in rows:
        event = dict(row)
        event["id"] = event.pop("audit_event_id")
        event["payload"] = _json_loads(event.pop("payload_json", "{}"), {})
        events.append(event)
    return events


def list_auth_profiles(
    *,
    workspace_id: str,
    provider: str = "",
    limit: int = 200,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    where: list[str] = ["workspace_id=?"]
    values: list[Any] = [workspace_id]
    if provider:
        where.append("provider=?")
        values.append(provider)
    sql = "SELECT * FROM auth_profiles WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT ?"
    values.append(max(1, int(limit)))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(values)).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = dict(row)
        payload["id"] = payload.pop("auth_profile_id")
        payload["scopes"] = _json_loads(payload.pop("scopes_json", "[]"), [])
        payload["metadata"] = _json_loads(payload.pop("metadata_json", "{}"), {})
        items.append(payload)
    return items


def list_policy_profiles(
    *,
    workspace_id: str,
    limit: int = 200,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM policy_profiles WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, max(1, int(limit))),
        ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = dict(row)
        payload["id"] = payload.pop("policy_profile_id")
        payload["rules"] = _json_loads(payload.pop("rules_json", "{}"), {})
        items.append(payload)
    return items
