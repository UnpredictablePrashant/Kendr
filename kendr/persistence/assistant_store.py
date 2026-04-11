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


def _slugify(name: str) -> str:
    import re

    slug = str(name or "").strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "assistant"


def _assistant_row_to_dict(row) -> dict:
    payload = dict(row)
    payload["attached_capabilities"] = _json_loads(payload.pop("attached_capabilities_json", "[]"), [])
    payload["memory_config"] = _json_loads(payload.pop("memory_config_json", "{}"), {})
    payload["metadata"] = _json_loads(payload.pop("metadata_json", "{}"), {})
    return payload


def _slug_exists(slug: str, *, db_path: str = DB_PATH, exclude_assistant_id: str = "") -> bool:
    initialize_db(db_path)
    sql = "SELECT 1 FROM assistants WHERE slug=?"
    values: list[Any] = [slug]
    if exclude_assistant_id:
        sql += " AND assistant_id != ?"
        values.append(exclude_assistant_id)
    sql += " LIMIT 1"
    with _connect(db_path) as conn:
        row = conn.execute(sql, tuple(values)).fetchone()
    return row is not None


def _unique_slug(name: str, *, db_path: str = DB_PATH, exclude_assistant_id: str = "") -> str:
    base = _slugify(name)
    slug = base
    idx = 1
    while _slug_exists(slug, db_path=db_path, exclude_assistant_id=exclude_assistant_id):
        slug = f"{base}-{idx}"
        idx += 1
    return slug


def list_assistants(
    *,
    workspace_id: str = "",
    status: str = "",
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
    if status:
        where.append("status=?")
        values.append(status)
    if search:
        like = f"%{search.lower()}%"
        where.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(goal) LIKE ? OR LOWER(slug) LIKE ?)")
        values.extend([like, like, like, like])
    sql = "SELECT * FROM assistants"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, LOWER(name) LIMIT ?"
    values.append(max(1, int(limit)))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(values)).fetchall()
    return [_assistant_row_to_dict(row) for row in rows]


def get_assistant(assistant_id: str, *, db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM assistants WHERE assistant_id=?", (assistant_id,)).fetchone()
    return _assistant_row_to_dict(row) if row else None


def create_assistant(
    *,
    workspace_id: str,
    owner_user_id: str,
    name: str,
    description: str = "",
    goal: str = "",
    system_prompt: str = "",
    model_provider: str = "",
    model_name: str = "",
    routing_policy: str = "balanced",
    status: str = "draft",
    attached_capabilities: list[dict] | None = None,
    memory_config: dict | None = None,
    metadata: dict | None = None,
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    assistant_id = str(uuid.uuid4())
    now = _utc_now()
    slug = _unique_slug(name, db_path=db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO assistants (
                assistant_id, workspace_id, owner_user_id, slug, name, description, goal,
                system_prompt, model_provider, model_name, routing_policy, status,
                attached_capabilities_json, memory_config_json, metadata_json,
                created_at, updated_at, last_tested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                assistant_id,
                workspace_id,
                owner_user_id,
                slug,
                name.strip(),
                description.strip(),
                goal.strip(),
                system_prompt.strip(),
                model_provider.strip(),
                model_name.strip(),
                routing_policy.strip() or "balanced",
                status.strip() or "draft",
                _json_dumps(attached_capabilities or []),
                _json_dumps(memory_config or {}),
                _json_dumps(metadata or {}),
                now,
                now,
            ),
        )
    return get_assistant(assistant_id, db_path=db_path) or {}


def update_assistant(
    assistant_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    goal: str | None = None,
    system_prompt: str | None = None,
    model_provider: str | None = None,
    model_name: str | None = None,
    routing_policy: str | None = None,
    status: str | None = None,
    attached_capabilities: list[dict] | None = None,
    memory_config: dict | None = None,
    metadata: dict | None = None,
    last_tested_at: str | None = None,
    db_path: str = DB_PATH,
) -> dict | None:
    initialize_db(db_path)
    current = get_assistant(assistant_id, db_path=db_path)
    if not current:
        return None
    updates: list[str] = []
    values: list[Any] = []
    if name is not None:
        updates.extend(["name=?", "slug=?"])
        values.extend([name.strip(), _unique_slug(name, db_path=db_path, exclude_assistant_id=assistant_id)])
    if description is not None:
        updates.append("description=?")
        values.append(description.strip())
    if goal is not None:
        updates.append("goal=?")
        values.append(goal.strip())
    if system_prompt is not None:
        updates.append("system_prompt=?")
        values.append(system_prompt.strip())
    if model_provider is not None:
        updates.append("model_provider=?")
        values.append(model_provider.strip())
    if model_name is not None:
        updates.append("model_name=?")
        values.append(model_name.strip())
    if routing_policy is not None:
        updates.append("routing_policy=?")
        values.append(routing_policy.strip() or "balanced")
    if status is not None:
        updates.append("status=?")
        values.append(status.strip() or "draft")
    if attached_capabilities is not None:
        updates.append("attached_capabilities_json=?")
        values.append(_json_dumps(attached_capabilities))
    if memory_config is not None:
        updates.append("memory_config_json=?")
        values.append(_json_dumps(memory_config))
    if metadata is not None:
        updates.append("metadata_json=?")
        values.append(_json_dumps(metadata))
    if last_tested_at is not None:
        updates.append("last_tested_at=?")
        values.append(last_tested_at)
    if not updates:
        return current
    updates.append("updated_at=?")
    values.append(_utc_now())
    values.append(assistant_id)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE assistants SET {', '.join(updates)} WHERE assistant_id=?", tuple(values))
    return get_assistant(assistant_id, db_path=db_path)


def delete_assistant(assistant_id: str, *, db_path: str = DB_PATH) -> bool:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM assistants WHERE assistant_id=?", (assistant_id,))
    return int(cur.rowcount or 0) > 0
