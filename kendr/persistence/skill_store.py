"""SQLite-backed persistence for user skills (catalog installs + custom skills)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .core import DB_PATH, _connect, initialize_db


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _j(v: Any) -> str:
    return json.dumps(v if v is not None else {}, ensure_ascii=False)


def _jl(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw) if str(raw or "").strip() else default
    except Exception:
        return default


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["tags"] = _jl(d.pop("tags", "[]"), [])
    d["metadata"] = _jl(d.pop("metadata", "{}"), {})
    d["input_schema"] = _jl(d.pop("input_schema", "{}"), {})
    d["output_schema"] = _jl(d.pop("output_schema", "{}"), {})
    d["is_installed"] = bool(d.get("is_installed", 0))
    return d


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_user_skill(
    *,
    name: str,
    slug: str,
    description: str = "",
    category: str = "Custom",
    icon: str = "",
    skill_type: str = "python",   # 'catalog' | 'python' | 'prompt'
    catalog_id: str = "",
    code: str = "",
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    is_installed: bool = True,
    status: str = "active",
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    skill_id = str(uuid.uuid4())
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_skills (
                skill_id, name, slug, description, category, icon,
                skill_type, catalog_id, code, input_schema, output_schema,
                is_installed, status, tags, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                skill_id, name, slug, description, category, icon,
                skill_type, catalog_id, code,
                _j(input_schema or {}), _j(output_schema or {}),
                1 if is_installed else 0, status,
                _j(tags or []), _j(metadata or {}), now, now,
            ),
        )
    return get_user_skill(skill_id=skill_id, db_path=db_path)  # type: ignore[return-value]


def get_user_skill(*, skill_id: str = "", slug: str = "", db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        if skill_id:
            row = conn.execute(
                "SELECT * FROM user_skills WHERE skill_id = ?", (skill_id,)
            ).fetchone()
        elif slug:
            row = conn.execute(
                "SELECT * FROM user_skills WHERE slug = ?", (slug,)
            ).fetchone()
        else:
            return None
    return _row_to_dict(row) if row else None


def list_user_skills(
    *,
    skill_type: str = "",
    is_installed: bool | None = None,
    category: str = "",
    status: str = "",
    q: str = "",
    limit: int = 500,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if skill_type:
        clauses.append("skill_type = ?")
        params.append(skill_type)
    if is_installed is not None:
        clauses.append("is_installed = ?")
        params.append(1 if is_installed else 0)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if q:
        like = f"%{q}%"
        clauses.append("(name LIKE ? OR description LIKE ? OR category LIKE ?)")
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM user_skills {where} ORDER BY name ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_user_skill(
    skill_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    icon: str | None = None,
    code: str | None = None,
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    status: str | None = None,
    db_path: str = DB_PATH,
) -> dict | None:
    initialize_db(db_path)
    sets: list[str] = ["updated_at = ?"]
    params: list[Any] = [_utc_now()]
    if name is not None:
        sets.append("name = ?"); params.append(name)
    if description is not None:
        sets.append("description = ?"); params.append(description)
    if category is not None:
        sets.append("category = ?"); params.append(category)
    if icon is not None:
        sets.append("icon = ?"); params.append(icon)
    if code is not None:
        sets.append("code = ?"); params.append(code)
    if input_schema is not None:
        sets.append("input_schema = ?"); params.append(_j(input_schema))
    if output_schema is not None:
        sets.append("output_schema = ?"); params.append(_j(output_schema))
    if tags is not None:
        sets.append("tags = ?"); params.append(_j(tags))
    if metadata is not None:
        sets.append("metadata = ?"); params.append(_j(metadata))
    if status is not None:
        sets.append("status = ?"); params.append(status)
    params.append(skill_id)
    with _connect(db_path) as conn:
        conn.execute(
            f"UPDATE user_skills SET {', '.join(sets)} WHERE skill_id = ?",
            params,
        )
    return get_user_skill(skill_id=skill_id, db_path=db_path)


def set_skill_installed(skill_id: str, installed: bool, db_path: str = DB_PATH) -> None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE user_skills SET is_installed = ?, updated_at = ? WHERE skill_id = ?",
            (1 if installed else 0, _utc_now(), skill_id),
        )


def delete_user_skill(skill_id: str, db_path: str = DB_PATH) -> bool:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM user_skills WHERE skill_id = ?", (skill_id,))
    return cur.rowcount > 0
