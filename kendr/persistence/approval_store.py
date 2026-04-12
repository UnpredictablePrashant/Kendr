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


def _row_to_dict(row) -> dict:
    payload = dict(row)
    payload["permissions"] = _json_loads(payload.pop("permissions_json", "{}"), {})
    payload["metadata"] = _json_loads(payload.pop("metadata_json", "{}"), {})
    return payload


def create_approval_grant(
    *,
    subject_type: str,
    subject_id: str,
    manifest_hash: str,
    scope: str,
    actor: str,
    note: str,
    session_id: str = "",
    permissions: dict | None = None,
    metadata: dict | None = None,
    db_path: str = DB_PATH,
) -> dict:
    initialize_db(db_path)
    now = _utc_now()
    grant_id = str(uuid.uuid4())
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO approval_grants (
                grant_id, subject_type, subject_id, manifest_hash, scope, session_id,
                actor, note, status, permissions_json, metadata_json,
                created_at, updated_at, last_used_at, use_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, NULL, 0)
            """,
            (
                grant_id,
                str(subject_type or "").strip(),
                str(subject_id or "").strip(),
                str(manifest_hash or "").strip(),
                str(scope or "").strip(),
                str(session_id or "").strip(),
                str(actor or "").strip(),
                str(note or "").strip(),
                _json_dumps(permissions or {}),
                _json_dumps(metadata or {}),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM approval_grants WHERE grant_id=?",
            (grant_id,),
        ).fetchone()
    return _row_to_dict(row)


def get_approval_grant(grant_id: str, *, db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT * FROM approval_grants WHERE grant_id=?", (grant_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_approval_grants(
    *,
    subject_type: str = "",
    subject_id: str = "",
    session_id: str = "",
    status: str = "",
    limit: int = 200,
    db_path: str = DB_PATH,
) -> list[dict]:
    initialize_db(db_path)
    where: list[str] = []
    params: list[Any] = []
    if subject_type:
        where.append("subject_type=?")
        params.append(subject_type)
    if subject_id:
        where.append("subject_id=?")
        params.append(subject_id)
    if session_id:
        where.append("session_id=?")
        params.append(session_id)
    if status:
        where.append("status=?")
        params.append(status)
    sql = "SELECT * FROM approval_grants"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(row) for row in rows]


def find_matching_approval_grant(
    *,
    subject_type: str,
    subject_id: str,
    manifest_hash: str,
    session_id: str = "",
    db_path: str = DB_PATH,
) -> dict | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM approval_grants
            WHERE subject_type=? AND subject_id=? AND manifest_hash=? AND status='active'
            ORDER BY
                CASE scope
                    WHEN 'once' THEN 0
                    WHEN 'session' THEN 1
                    WHEN 'always' THEN 2
                    ELSE 3
                END,
                updated_at DESC
            """,
            (
                str(subject_type or "").strip(),
                str(subject_id or "").strip(),
                str(manifest_hash or "").strip(),
            ),
        ).fetchall()
    requested_session = str(session_id or "").strip()
    for row in rows:
        item = _row_to_dict(row)
        scope = str(item.get("scope", "") or "").strip().lower()
        grant_session = str(item.get("session_id", "") or "").strip()
        if scope == "always":
            return item
        if scope == "session":
            if requested_session and grant_session == requested_session:
                return item
            continue
        if scope == "once":
            if not grant_session or (requested_session and grant_session == requested_session):
                return item
    return None


def consume_approval_grant(grant_id: str, *, db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    current = get_approval_grant(grant_id, db_path=db_path)
    if not current:
        return None
    now = _utc_now()
    next_status = "used" if str(current.get("scope", "")).strip().lower() == "once" else str(current.get("status", "active") or "active")
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE approval_grants
            SET status=?, last_used_at=?, use_count=?, updated_at=?
            WHERE grant_id=?
            """,
            (
                next_status,
                now,
                int(current.get("use_count", 0) or 0) + 1,
                now,
                grant_id,
            ),
        )
    return get_approval_grant(grant_id, db_path=db_path)


def revoke_approval_grant(grant_id: str, *, db_path: str = DB_PATH) -> dict | None:
    initialize_db(db_path)
    if not get_approval_grant(grant_id, db_path=db_path):
        return None
    now = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE approval_grants SET status='revoked', updated_at=? WHERE grant_id=?",
            (now, grant_id),
        )
    return get_approval_grant(grant_id, db_path=db_path)
