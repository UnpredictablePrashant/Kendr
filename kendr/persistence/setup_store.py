from __future__ import annotations

import json

from .core import DB_PATH, _connect, initialize_db
from kendr.secret_store import build_secret_ref, delete_secret, get_secret, is_secret_ref, put_secret


def _setup_secret_ref(component_id: str, config_key: str) -> str:
    return build_secret_ref("setup", component_id, config_key)


def _provider_secret_ref(provider: str) -> str:
    return build_secret_ref("provider", provider, "tokens")


def _get_raw_setup_config_row(component_id: str, config_key: str, db_path: str) -> dict:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT component_id, config_key, config_value, is_secret, updated_at
            FROM setup_config_values
            WHERE component_id = ? AND config_key = ?
            """,
            (component_id, config_key),
        ).fetchone()
    return dict(row) if row else {}


def _resolve_setup_secret(component_id: str, config_key: str, raw_value: str, db_path: str) -> tuple[str, str]:
    text = str(raw_value or "")
    if not text:
        return "", ""
    if is_secret_ref(text):
        resolved = get_secret(text, default="")
        return (str(resolved or ""), text)
    ref = _setup_secret_ref(component_id, config_key)
    try:
        put_secret(ref, text)
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE setup_config_values
                SET config_value = ?, is_secret = 1
                WHERE component_id = ? AND config_key = ?
                """,
                (ref, component_id, config_key),
            )
        return text, ref
    except Exception:
        return text, ""


def _store_setup_secret(component_id: str, config_key: str, config_value: str) -> str:
    ref = _setup_secret_ref(component_id, config_key)
    put_secret(ref, config_value)
    return ref


def _parse_provider_token_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _resolve_provider_tokens(provider: str, raw_token_json: str, updated_at: str, db_path: str) -> dict:
    payload = _parse_provider_token_payload(raw_token_json)
    secret_ref = str(payload.get("secret_ref", "") or "").strip()
    if is_secret_ref(secret_ref):
        resolved = get_secret(secret_ref, default={})
        return resolved if isinstance(resolved, dict) else {}
    if not payload:
        return {}
    ref = _provider_secret_ref(provider)
    try:
        put_secret(ref, payload)
        with _connect(db_path) as conn:
            conn.execute(
                """
                UPDATE setup_provider_tokens
                SET token_json = ?, updated_at = ?
                WHERE provider = ?
                """,
                (json.dumps({"secret_ref": ref}, ensure_ascii=False), updated_at, provider),
            )
        return payload
    except Exception:
        return payload


def upsert_setup_component(
    component_id: str,
    *,
    enabled: bool = True,
    notes: str = "",
    updated_at: str = "",
    db_path: str = DB_PATH,
):
    initialize_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO setup_components (component_id, enabled, notes, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(component_id) DO UPDATE SET
                enabled=excluded.enabled,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            (component_id, 1 if enabled else 0, notes, updated_at),
        )


def get_setup_component(component_id: str, db_path: str = DB_PATH) -> dict:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT component_id, enabled, notes, updated_at
            FROM setup_components
            WHERE component_id = ?
            """,
            (component_id,),
        ).fetchone()
    return dict(row) if row else {}


def list_setup_components(db_path: str = DB_PATH) -> list[dict]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT component_id, enabled, notes, updated_at
            FROM setup_components
            ORDER BY component_id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def upsert_setup_config_value(
    component_id: str,
    config_key: str,
    config_value: str,
    *,
    is_secret: bool = False,
    updated_at: str = "",
    db_path: str = DB_PATH,
):
    initialize_db(db_path)
    existing = _get_raw_setup_config_row(component_id, config_key, db_path)
    stored_value = config_value
    if is_secret:
        stored_value = config_value if is_secret_ref(config_value) else _store_setup_secret(component_id, config_key, config_value)
    old_value = str(existing.get("config_value", "") or "")
    if old_value and is_secret_ref(old_value) and old_value != stored_value:
        delete_secret(old_value)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO setup_config_values (component_id, config_key, config_value, is_secret, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(component_id, config_key) DO UPDATE SET
                config_value=excluded.config_value,
                is_secret=excluded.is_secret,
                updated_at=excluded.updated_at
            """,
            (component_id, config_key, stored_value, 1 if is_secret else 0, updated_at),
        )


def delete_setup_config_value(component_id: str, config_key: str, db_path: str = DB_PATH):
    existing = _get_raw_setup_config_row(component_id, config_key, db_path)
    old_value = str(existing.get("config_value", "") or "")
    if is_secret_ref(old_value):
        delete_secret(old_value)
    initialize_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            DELETE FROM setup_config_values
            WHERE component_id = ? AND config_key = ?
            """,
            (component_id, config_key),
        )


def list_setup_config_values(*, include_secrets: bool = True, db_path: str = DB_PATH) -> list[dict]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT component_id, config_key, config_value, is_secret, updated_at
            FROM setup_config_values
            ORDER BY component_id ASC, config_key ASC
            """
        ).fetchall()
    payload = []
    for row in rows:
        item = dict(row)
        if int(item.get("is_secret", 0)) == 1:
            resolved, ref = _resolve_setup_secret(
                str(item.get("component_id", "")),
                str(item.get("config_key", "")),
                str(item.get("config_value", "")),
                db_path,
            )
            item["secret_ref"] = ref
            item["config_value"] = resolved if include_secrets else ("********" if resolved else "")
        payload.append(item)
    return payload


def get_setup_config_value(component_id: str, config_key: str, db_path: str = DB_PATH) -> dict:
    item = _get_raw_setup_config_row(component_id, config_key, db_path)
    if not item:
        return {}
    if int(item.get("is_secret", 0)) == 1:
        resolved, ref = _resolve_setup_secret(component_id, config_key, str(item.get("config_value", "")), db_path)
        item["secret_ref"] = ref
        item["config_value"] = resolved
    return item


def set_setup_provider_tokens(provider: str, token_payload: dict, updated_at: str = "", db_path: str = DB_PATH):
    initialize_db(db_path)
    ref = _provider_secret_ref(provider)
    put_secret(ref, token_payload if isinstance(token_payload, dict) else {})
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO setup_provider_tokens (provider, token_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                token_json=excluded.token_json,
                updated_at=excluded.updated_at
            """,
            (provider, json.dumps({"secret_ref": ref}, ensure_ascii=False), updated_at),
        )


def get_setup_provider_tokens(provider: str, db_path: str = DB_PATH) -> dict:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT token_json
            FROM setup_provider_tokens
            WHERE provider = ?
            """,
            (provider,),
        ).fetchone()
    if not row:
        return {}
    return _resolve_provider_tokens(provider, str(row["token_json"] or ""), "", db_path)


def list_setup_provider_tokens(*, include_secrets: bool = False, db_path: str = DB_PATH) -> dict:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT provider, token_json, updated_at
            FROM setup_provider_tokens
            ORDER BY provider ASC
            """
        ).fetchall()
    payload: dict[str, dict] = {}
    for row in rows:
        provider = row["provider"]
        value = _resolve_provider_tokens(provider, str(row["token_json"] or ""), str(row["updated_at"] or ""), db_path)
        if not include_secrets and isinstance(value, dict):
            scrubbed = {}
            for key, token_value in value.items():
                if "token" in key or "secret" in key:
                    scrubbed[key] = "********"
                else:
                    scrubbed[key] = token_value
            value = scrubbed
        payload[provider] = {
            "token_payload": value,
            "updated_at": row["updated_at"],
        }
    return payload


def insert_privileged_audit_event(event: dict, db_path: str = DB_PATH):
    initialize_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO privileged_audit_events (
                event_id, run_id, timestamp, actor, action, status, detail_json, prev_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("event_id", ""),
                event.get("run_id", ""),
                event.get("timestamp", ""),
                event.get("actor", ""),
                event.get("action", ""),
                event.get("status", ""),
                json.dumps(event.get("detail", {}), ensure_ascii=False),
                event.get("prev_hash", ""),
                event.get("event_hash", ""),
            ),
        )


def list_privileged_audit_events(limit: int = 100, db_path: str = DB_PATH) -> list[dict]:
    initialize_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_id, run_id, timestamp, actor, action, status, detail_json, prev_hash, event_hash
            FROM privileged_audit_events
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    payload: list[dict] = []
    for row in rows:
        item = dict(row)
        try:
            item["detail"] = json.loads(item.get("detail_json") or "{}")
        except Exception:
            item["detail"] = {}
        payload.append(item)
    return payload
