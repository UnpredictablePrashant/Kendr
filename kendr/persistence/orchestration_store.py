from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .core import DB_PATH, _connect, initialize_db


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except Exception:
        return default


def replace_intent_candidates(
    run_id: str,
    candidates: list[dict[str, Any]],
    *,
    objective_signature: str,
    db_path: str = DB_PATH,
) -> list[dict[str, Any]]:
    initialize_db(db_path)
    created_at = _utc_now()
    with _connect(db_path) as conn:
        conn.execute(
            """
            DELETE FROM intent_candidates
            WHERE run_id = ? AND objective_signature = ?
            """,
            (run_id, objective_signature),
        )
        for index, candidate in enumerate(candidates):
            conn.execute(
                """
                INSERT OR REPLACE INTO intent_candidates (
                    intent_id,
                    run_id,
                    created_at,
                    objective_signature,
                    intent_type,
                    label,
                    score,
                    selected,
                    execution_mode,
                    requires_planner,
                    risk_level,
                    reasons_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(candidate.get("intent_id", "")).strip() or f"{run_id}:intent:{objective_signature}:{index}",
                    run_id,
                    str(candidate.get("created_at", "")).strip() or created_at,
                    objective_signature,
                    str(candidate.get("intent_type", "")).strip(),
                    str(candidate.get("label", "")).strip(),
                    int(candidate.get("score", 0) or 0),
                    1 if candidate.get("selected") else 0,
                    str(candidate.get("execution_mode", "adaptive")).strip() or "adaptive",
                    1 if candidate.get("requires_planner") else 0,
                    str(candidate.get("risk_level", "low")).strip() or "low",
                    json.dumps(candidate.get("reasons", []), ensure_ascii=False),
                    json.dumps(candidate.get("metadata", {}), ensure_ascii=False),
                ),
            )
        rows = conn.execute(
            """
            SELECT intent_id, run_id, created_at, objective_signature, intent_type, label, score, selected,
                   execution_mode, requires_planner, risk_level, reasons_json, metadata_json
            FROM intent_candidates
            WHERE run_id = ? AND objective_signature = ?
            ORDER BY selected DESC, score DESC, created_at ASC
            """,
            (run_id, objective_signature),
        ).fetchall()
    return _decode_intent_rows(rows)


def list_intent_candidates(run_id: str, *, objective_signature: str = "", db_path: str = DB_PATH) -> list[dict[str, Any]]:
    initialize_db(db_path)
    sql = """
        SELECT intent_id, run_id, created_at, objective_signature, intent_type, label, score, selected,
               execution_mode, requires_planner, risk_level, reasons_json, metadata_json
        FROM intent_candidates
        WHERE run_id = ?
    """
    params: list[Any] = [run_id]
    if objective_signature:
        sql += " AND objective_signature = ?"
        params.append(objective_signature)
    sql += " ORDER BY created_at DESC, selected DESC, score DESC"
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return _decode_intent_rows(rows)


def upsert_execution_plan(
    plan_id: str,
    *,
    run_id: str,
    intent_id: str = "",
    version: int = 1,
    status: str = "draft",
    approval_status: str = "not_started",
    needs_clarification: bool = False,
    objective: str = "",
    summary: str = "",
    plan_markdown: str = "",
    plan_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    initialize_db(db_path)
    timestamp = _utc_now()
    payload = dict(plan_data or {})
    meta = dict(metadata or {})
    with _connect(db_path) as conn:
        conn.execute(
            """
            UPDATE execution_plans
            SET status = CASE
                WHEN status IN ('completed', 'failed', 'cancelled') THEN status
                ELSE 'superseded'
            END,
                updated_at = ?
            WHERE run_id = ? AND plan_id != ? AND version < ?
            """,
            (timestamp, run_id, plan_id, int(version or 1)),
        )
        conn.execute(
            """
            INSERT INTO execution_plans (
                plan_id,
                run_id,
                intent_id,
                version,
                status,
                approval_status,
                needs_clarification,
                objective,
                summary,
                plan_markdown,
                plan_json,
                metadata_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                intent_id=excluded.intent_id,
                version=excluded.version,
                status=excluded.status,
                approval_status=excluded.approval_status,
                needs_clarification=excluded.needs_clarification,
                objective=excluded.objective,
                summary=excluded.summary,
                plan_markdown=excluded.plan_markdown,
                plan_json=excluded.plan_json,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                plan_id,
                run_id,
                intent_id,
                int(version or 1),
                status,
                approval_status,
                1 if needs_clarification else 0,
                objective,
                summary,
                plan_markdown,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(meta, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            """
            SELECT plan_id, run_id, intent_id, version, status, approval_status, needs_clarification, objective,
                   summary, plan_markdown, plan_json, metadata_json, created_at, updated_at
            FROM execution_plans
            WHERE plan_id = ?
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone()
    return _decode_plan_row(row)


def update_execution_plan_status(
    plan_id: str,
    *,
    status: str | None = None,
    approval_status: str | None = None,
    needs_clarification: bool | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str = DB_PATH,
) -> dict[str, Any] | None:
    initialize_db(db_path)
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [_utc_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if approval_status is not None:
        fields.append("approval_status = ?")
        values.append(approval_status)
    if needs_clarification is not None:
        fields.append("needs_clarification = ?")
        values.append(1 if needs_clarification else 0)
    values.append(plan_id)
    with _connect(db_path) as conn:
        if metadata is not None:
            current_row = conn.execute(
                "SELECT metadata_json FROM execution_plans WHERE plan_id = ? LIMIT 1",
                (plan_id,),
            ).fetchone()
            current_metadata = _json_loads(current_row["metadata_json"], {}) if current_row else {}
            merged_metadata = dict(current_metadata if isinstance(current_metadata, dict) else {})
            merged_metadata.update(dict(metadata))
            fields.append("metadata_json = ?")
            values.insert(len(values) - 1, json.dumps(merged_metadata, ensure_ascii=False))
        conn.execute(f"UPDATE execution_plans SET {', '.join(fields)} WHERE plan_id = ?", values)
        row = conn.execute(
            """
            SELECT plan_id, run_id, intent_id, version, status, approval_status, needs_clarification, objective,
                   summary, plan_markdown, plan_json, metadata_json, created_at, updated_at
            FROM execution_plans
            WHERE plan_id = ?
            LIMIT 1
            """,
            (plan_id,),
        ).fetchone()
    return _decode_plan_row(row) if row else None


def get_latest_execution_plan(run_id: str, *, db_path: str = DB_PATH) -> dict[str, Any] | None:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT plan_id, run_id, intent_id, version, status, approval_status, needs_clarification, objective,
                   summary, plan_markdown, plan_json, metadata_json, created_at, updated_at
            FROM execution_plans
            WHERE run_id = ?
            ORDER BY version DESC, updated_at DESC
            LIMIT 1
            """,
            (run_id,),
        ).fetchone()
    return _decode_plan_row(row) if row else None


def list_execution_plans(run_id: str, *, db_path: str = DB_PATH) -> list[dict[str, Any]]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT plan_id, run_id, intent_id, version, status, approval_status, needs_clarification, objective,
                   summary, plan_markdown, plan_json, metadata_json, created_at, updated_at
            FROM execution_plans
            WHERE run_id = ?
            ORDER BY version DESC, updated_at DESC
            """,
            (run_id,),
        ).fetchall()
    return [_decode_plan_row(row) for row in rows]


def replace_plan_tasks(plan_id: str, run_id: str, steps: list[dict[str, Any]], *, db_path: str = DB_PATH) -> list[dict[str, Any]]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM task_dependencies WHERE plan_id = ?", (plan_id,))
        conn.execute("DELETE FROM plan_tasks WHERE plan_id = ?", (plan_id,))
        for index, step in enumerate(steps):
            step_id = str(step.get("id", "")).strip() or f"step-{index + 1}"
            plan_task_id = str(step.get("plan_task_id", "")).strip() or _plan_task_id(plan_id, step_id)
            conn.execute(
                """
                INSERT INTO plan_tasks (
                    plan_task_id,
                    plan_id,
                    run_id,
                    step_id,
                    parent_step_id,
                    step_index,
                    title,
                    agent_name,
                    task_content,
                    success_criteria,
                    rationale,
                    parallel_group,
                    side_effect_level,
                    conflict_keys_json,
                    status,
                    lease_owner,
                    lease_expires_at,
                    attempt_count,
                    last_attempt_at,
                    started_at,
                    completed_at,
                    result_summary,
                    error_text,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_task_id,
                    plan_id,
                    run_id,
                    step_id,
                    str(step.get("parent_step_id", "")).strip(),
                    int(step.get("step_index", index) or index),
                    str(step.get("title", "")).strip(),
                    str(step.get("agent", "")).strip(),
                    str(step.get("task", "")).strip(),
                    str(step.get("success_criteria", step.get("success", ""))).strip(),
                    str(step.get("rationale", "")).strip(),
                    str(step.get("parallel_group", "")).strip(),
                    str(step.get("side_effect_level", "unknown")).strip() or "unknown",
                    json.dumps(step.get("conflict_keys", []), ensure_ascii=False),
                    str(step.get("status", "pending")).strip() or "pending",
                    str(step.get("lease_owner", "")).strip(),
                    _nullable_text(step.get("lease_expires_at")),
                    int(step.get("attempt_count", 0) or 0),
                    _nullable_text(step.get("last_attempt_at")),
                    _nullable_text(step.get("started_at")),
                    _nullable_text(step.get("completed_at")),
                    _nullable_text(step.get("result_summary")),
                    _nullable_text(step.get("error")),
                    json.dumps(
                        {
                            "depends_on": step.get("depends_on", []),
                            "substeps": step.get("substeps", []),
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            for dependency in _as_str_list(step.get("depends_on", [])):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO task_dependencies (plan_id, step_id, depends_on_step_id)
                    VALUES (?, ?, ?)
                    """,
                    (plan_id, step_id, dependency),
                )
        rows = conn.execute(
            """
            SELECT plan_task_id, plan_id, run_id, step_id, parent_step_id, step_index, title, agent_name,
                   task_content, success_criteria, rationale, parallel_group, side_effect_level, conflict_keys_json,
                   status, lease_owner, lease_expires_at, attempt_count, last_attempt_at, started_at, completed_at,
                   result_summary, error_text, metadata_json
            FROM plan_tasks
            WHERE plan_id = ?
            ORDER BY step_index ASC
            """,
            (plan_id,),
        ).fetchall()
    return _decode_plan_task_rows(rows)


def list_plan_tasks(*, plan_id: str = "", run_id: str = "", db_path: str = DB_PATH) -> list[dict[str, Any]]:
    initialize_db(db_path)
    clauses: list[str] = []
    params: list[Any] = []
    if plan_id:
        clauses.append("plan_id = ?")
        params.append(plan_id)
    if run_id:
        clauses.append("run_id = ?")
        params.append(run_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT plan_task_id, plan_id, run_id, step_id, parent_step_id, step_index, title, agent_name,
                   task_content, success_criteria, rationale, parallel_group, side_effect_level, conflict_keys_json,
                   status, lease_owner, lease_expires_at, attempt_count, last_attempt_at, started_at, completed_at,
                   result_summary, error_text, metadata_json
            FROM plan_tasks
            {where}
            ORDER BY step_index ASC
            """,
            params,
        ).fetchall()
    return _decode_plan_task_rows(rows)


def update_plan_task_state(
    plan_id: str,
    step_id: str,
    *,
    status: str,
    started_at: str | None = None,
    completed_at: str | None = None,
    result_summary: str | None = None,
    error_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str = DB_PATH,
) -> dict[str, Any] | None:
    initialize_db(db_path)
    fields = ["status = ?"]
    values: list[Any] = [status]
    if started_at is not None:
        fields.append("started_at = ?")
        values.append(started_at)
    if completed_at is not None:
        fields.append("completed_at = ?")
        values.append(completed_at)
    if result_summary is not None:
        fields.append("result_summary = ?")
        values.append(result_summary)
    if error_text is not None:
        fields.append("error_text = ?")
        values.append(error_text)
    values.extend([plan_id, step_id])
    with _connect(db_path) as conn:
        if metadata is not None:
            current_row = conn.execute(
                """
                SELECT metadata_json
                FROM plan_tasks
                WHERE plan_id = ? AND step_id = ?
                LIMIT 1
                """,
                (plan_id, step_id),
            ).fetchone()
            current_metadata = _json_loads(current_row["metadata_json"], {}) if current_row else {}
            merged_metadata = dict(current_metadata if isinstance(current_metadata, dict) else {})
            merged_metadata.update(dict(metadata))
            fields.append("metadata_json = ?")
            values.insert(len(values) - 2, json.dumps(merged_metadata, ensure_ascii=False))
        conn.execute(
            f"""
            UPDATE plan_tasks
            SET {', '.join(fields)}
            WHERE plan_id = ? AND step_id = ?
            """,
            values,
        )
        row = conn.execute(
            """
            SELECT plan_task_id, plan_id, run_id, step_id, parent_step_id, step_index, title, agent_name,
                   task_content, success_criteria, rationale, parallel_group, side_effect_level, conflict_keys_json,
                   status, lease_owner, lease_expires_at, attempt_count, last_attempt_at, started_at, completed_at,
                   result_summary, error_text, metadata_json
            FROM plan_tasks
            WHERE plan_id = ? AND step_id = ?
            LIMIT 1
            """,
            (plan_id, step_id),
        ).fetchone()
    return _decode_plan_task_rows([row])[0] if row else None


def claim_plan_task(
    plan_id: str,
    step_id: str,
    *,
    lease_owner: str,
    lease_seconds: int = 300,
    db_path: str = DB_PATH,
) -> dict[str, Any] | None:
    initialize_db(db_path)
    now = _utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=max(30, int(lease_seconds or 300)))).isoformat()
    with _connect(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE plan_tasks
            SET lease_owner = ?,
                lease_expires_at = ?,
                attempt_count = COALESCE(attempt_count, 0) + 1,
                last_attempt_at = ?,
                started_at = CASE
                    WHEN status IN ('pending', 'queued', 'ready', 'waiting') AND COALESCE(started_at, '') = '' THEN ?
                    ELSE started_at
                END,
                status = CASE
                    WHEN status IN ('pending', 'queued', 'ready', 'waiting') THEN 'running'
                    ELSE status
                END
            WHERE plan_id = ?
              AND step_id = ?
              AND status NOT IN ('completed', 'failed', 'blocked', 'cancelled')
              AND (
                    COALESCE(lease_owner, '') = ''
                    OR lease_owner = ?
                    OR COALESCE(lease_expires_at, '') = ''
                    OR lease_expires_at < ?
              )
            """,
            (lease_owner, expires_at, now, now, plan_id, step_id, lease_owner, now),
        )
        if int(cursor.rowcount or 0) <= 0:
            return None
        row = conn.execute(
            """
            SELECT plan_task_id, plan_id, run_id, step_id, parent_step_id, step_index, title, agent_name,
                   task_content, success_criteria, rationale, parallel_group, side_effect_level, conflict_keys_json,
                   status, lease_owner, lease_expires_at, attempt_count, last_attempt_at, started_at, completed_at,
                   result_summary, error_text, metadata_json
            FROM plan_tasks
            WHERE plan_id = ? AND step_id = ?
            LIMIT 1
            """,
            (plan_id, step_id),
        ).fetchone()
    return _decode_plan_task_rows([row])[0] if row else None


def release_plan_task_lease(
    plan_id: str,
    step_id: str,
    *,
    lease_owner: str = "",
    db_path: str = DB_PATH,
) -> None:
    initialize_db(db_path)
    sql = """
        UPDATE plan_tasks
        SET lease_owner = '',
            lease_expires_at = NULL
        WHERE plan_id = ? AND step_id = ?
    """
    params: list[Any] = [plan_id, step_id]
    if lease_owner:
        sql += " AND lease_owner = ?"
        params.append(lease_owner)
    with _connect(db_path) as conn:
        conn.execute(sql, params)


def list_task_dependencies(plan_id: str, *, db_path: str = DB_PATH) -> list[dict[str, Any]]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT plan_id, step_id, depends_on_step_id
            FROM task_dependencies
            WHERE plan_id = ?
            ORDER BY step_id ASC, depends_on_step_id ASC
            """,
            (plan_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def insert_orchestration_event(
    event: dict[str, Any],
    *,
    db_path: str = DB_PATH,
) -> dict[str, Any]:
    initialize_db(db_path)
    payload = dict(event)
    payload.setdefault("event_id", f"evt_{_utc_now()}_{abs(hash(json.dumps(payload, sort_keys=True, default=str))) % 1_000_000}")
    payload.setdefault("timestamp", _utc_now())
    payload.setdefault("plan_id", "")
    payload.setdefault("status", "")
    payload.setdefault("source", "")
    payload.setdefault("payload", {})
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO orchestration_events (
                event_id,
                run_id,
                plan_id,
                subject_type,
                subject_id,
                event_type,
                status,
                source,
                timestamp,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("event_id", "")).strip(),
                str(payload.get("run_id", "")).strip(),
                str(payload.get("plan_id", "")).strip(),
                str(payload.get("subject_type", "")).strip(),
                str(payload.get("subject_id", "")).strip(),
                str(payload.get("event_type", "")).strip(),
                str(payload.get("status", "")).strip(),
                str(payload.get("source", "")).strip(),
                str(payload.get("timestamp", "")).strip() or _utc_now(),
                json.dumps(payload.get("payload", {}), ensure_ascii=False),
            ),
        )
        row = conn.execute(
            """
            SELECT event_id, run_id, plan_id, subject_type, subject_id, event_type, status, source, timestamp, payload_json
            FROM orchestration_events
            WHERE event_id = ?
            LIMIT 1
            """,
            (str(payload.get("event_id", "")).strip(),),
        ).fetchone()
    return _decode_event_row(row)


def list_orchestration_events(run_id: str, *, limit: int = 200, db_path: str = DB_PATH) -> list[dict[str, Any]]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_id, run_id, plan_id, subject_type, subject_id, event_type, status, source, timestamp, payload_json
            FROM orchestration_events
            WHERE run_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
    return [_decode_event_row(row) for row in rows]


def list_recent_orchestration_events(
    *,
    since_timestamp: str = "",
    limit: int = 200,
    db_path: str = DB_PATH,
) -> list[dict[str, Any]]:
    initialize_db(db_path)
    sql = """
        SELECT event_id, run_id, plan_id, subject_type, subject_id, event_type, status, source, timestamp, payload_json
        FROM orchestration_events
    """
    params: list[Any] = []
    if str(since_timestamp or "").strip():
        sql += " WHERE timestamp > ?"
        params.append(str(since_timestamp).strip())
    sql += " ORDER BY timestamp ASC LIMIT ?"
    params.append(int(limit or 200))
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_decode_event_row(row) for row in rows]


def _plan_task_id(plan_id: str, step_id: str) -> str:
    return f"{plan_id}:task:{step_id}"


def _nullable_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _decode_intent_rows(rows: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["selected"] = bool(item.get("selected"))
        item["requires_planner"] = bool(item.get("requires_planner"))
        item["reasons"] = _json_loads(item.pop("reasons_json", ""), [])
        item["metadata"] = _json_loads(item.pop("metadata_json", ""), {})
        items.append(item)
    return items


def _decode_plan_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["needs_clarification"] = bool(item.get("needs_clarification"))
    item["plan_data"] = _json_loads(item.pop("plan_json", ""), {})
    item["metadata"] = _json_loads(item.pop("metadata_json", ""), {})
    return item


def _decode_plan_task_rows(rows: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        metadata = _json_loads(item.pop("metadata_json", ""), {})
        conflict_keys = _json_loads(item.pop("conflict_keys_json", ""), [])
        if not isinstance(conflict_keys, list):
            conflict_keys = []
        depends_on = metadata.get("depends_on", [])
        if not isinstance(depends_on, list):
            depends_on = []
        item["depends_on"] = [str(entry).strip() for entry in depends_on if str(entry).strip()]
        item["conflict_keys"] = [str(entry).strip() for entry in conflict_keys if str(entry).strip()]
        item["metadata"] = metadata
        item["agent"] = item.pop("agent_name", "")
        item["task"] = item.pop("task_content", "")
        item["error"] = item.pop("error_text", "")
        items.append(item)
    return items


def _decode_event_row(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["payload"] = _json_loads(item.pop("payload_json", ""), {})
    return item
