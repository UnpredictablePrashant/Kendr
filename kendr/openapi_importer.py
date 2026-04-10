"""OpenAPI -> capability registry importer (Phase 2)."""

from __future__ import annotations

import json
import re
from typing import Any

from kendr.capability_registry import CapabilityRegistryService
from kendr.persistence import get_capability_by_key, list_capabilities


_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_") or "item"


def parse_openapi_payload(*, spec: dict | None = None, spec_text: str = "") -> dict:
    if isinstance(spec, dict):
        return spec
    raw = str(spec_text or "").strip()
    if not raw:
        raise ValueError("OpenAPI payload is empty.")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception as exc:
        raise ValueError(f"Unable to parse OpenAPI payload as JSON or YAML: {exc}") from exc
    raise ValueError("OpenAPI payload must be a JSON/YAML object.")


def _extract_response_schema(operation: dict) -> dict:
    responses = operation.get("responses", {}) if isinstance(operation.get("responses", {}), dict) else {}
    for code in ("200", "201", "default"):
        resp = responses.get(code, {})
        if not isinstance(resp, dict):
            continue
        content = resp.get("content", {})
        if not isinstance(content, dict):
            continue
        app_json = content.get("application/json", {})
        if isinstance(app_json, dict):
            schema = app_json.get("schema", {})
            if isinstance(schema, dict) and schema:
                return schema
    return {}


def _extract_input_schema(operation: dict) -> dict:
    params = operation.get("parameters", []) if isinstance(operation.get("parameters", []), list) else []
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in params:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        schema = p.get("schema", {})
        properties[name] = schema if isinstance(schema, dict) else {"type": "string"}
        if bool(p.get("required", False)):
            required.append(name)

    request_body = operation.get("requestBody", {})
    if isinstance(request_body, dict):
        content = request_body.get("content", {})
        if isinstance(content, dict):
            app_json = content.get("application/json", {})
            if isinstance(app_json, dict):
                body_schema = app_json.get("schema", {})
                if isinstance(body_schema, dict) and body_schema:
                    properties["body"] = body_schema
                    if bool(request_body.get("required", False)):
                        required.append("body")
    payload = {"type": "object", "properties": properties}
    if required:
        payload["required"] = sorted(set(required))
    return payload


def import_openapi_as_capabilities(
    *,
    workspace_id: str,
    owner_user_id: str,
    openapi_spec: dict,
    auth_profile_id: str = "",
    policy_profile_id: str = "",
    visibility: str = "workspace",
    status: str = "draft",
    db_path: str = "",
) -> dict:
    paths = openapi_spec.get("paths", {})
    if not isinstance(paths, dict) or not paths:
        raise ValueError("OpenAPI document must include a non-empty 'paths' object.")

    info = openapi_spec.get("info", {}) if isinstance(openapi_spec.get("info", {}), dict) else {}
    api_title = str(info.get("title", "")).strip() or "Imported API"
    api_slug = _slug(api_title)
    service_key = f"api.service.{api_slug}"
    service = CapabilityRegistryService(db_path=db_path)

    service_meta = {
        "managed_by": "openapi_import",
        "managed_type": "api_service",
        "openapi_version": str(openapi_spec.get("openapi") or openapi_spec.get("swagger") or ""),
        "api_title": api_title,
    }
    existing_service = get_capability_by_key(
        workspace_id=workspace_id,
        key=service_key,
        db_path=db_path,
    )
    if existing_service:
        service_cap = service.update(
            existing_service["id"],
            actor_user_id=owner_user_id,
            workspace_id=workspace_id,
            name=api_title,
            description=str(info.get("description", "")).strip() or f"Imported API service: {api_title}",
            status=status,
            visibility=visibility,
            tags=["api", "openapi", "service"],
            metadata=service_meta,
            schema_in={"type": "object"},
            schema_out={"type": "object"},
            auth_profile_id=auth_profile_id or None,
            policy_profile_id=policy_profile_id or None,
        ) or existing_service
    else:
        service_cap = service.create(
            workspace_id=workspace_id,
            capability_type="api",
            key=service_key,
            name=api_title,
            description=str(info.get("description", "")).strip() or f"Imported API service: {api_title}",
            owner_user_id=owner_user_id,
            visibility=visibility,
            status=status,
            tags=["api", "openapi", "service"],
            metadata=service_meta,
            schema_in={"type": "object"},
            schema_out={"type": "object"},
            auth_profile_id=auth_profile_id,
            policy_profile_id=policy_profile_id,
        )

    seen_keys = {service_key}
    operations_synced = 0
    operations_created = 0

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in _HTTP_METHODS:
            if method not in path_item:
                continue
            operation = path_item.get(method, {})
            if not isinstance(operation, dict) or not operation:
                continue
            operation_id = str(operation.get("operationId", "")).strip()
            op_slug = _slug(operation_id or f"{method}_{path}")
            op_key = f"api.operation.{api_slug}.{method}.{op_slug}"
            seen_keys.add(op_key)
            description = str(operation.get("summary", "")).strip() or str(operation.get("description", "")).strip()
            description = description or f"{method.upper()} {path}"
            op_meta = {
                "managed_by": "openapi_import",
                "managed_type": "api_operation",
                "openapi_api_slug": api_slug,
                "api_title": api_title,
                "method": method.upper(),
                "path": path,
                "operation_id": operation_id,
            }
            schema_in = _extract_input_schema(operation)
            schema_out = _extract_response_schema(operation) or {"type": "object"}

            existing_op = get_capability_by_key(
                workspace_id=workspace_id,
                key=op_key,
                db_path=db_path,
            )
            if existing_op:
                op_cap = service.update(
                    existing_op["id"],
                    actor_user_id=owner_user_id,
                    workspace_id=workspace_id,
                    name=operation_id or f"{method.upper()} {path}",
                    description=description,
                    status=status,
                    visibility=visibility,
                    tags=["api", "openapi", "operation"],
                    metadata=op_meta,
                    schema_in=schema_in,
                    schema_out=schema_out,
                    auth_profile_id=auth_profile_id or None,
                    policy_profile_id=policy_profile_id or None,
                ) or existing_op
            else:
                op_cap = service.create(
                    workspace_id=workspace_id,
                    capability_type="tool",
                    key=op_key,
                    name=operation_id or f"{method.upper()} {path}",
                    description=description,
                    owner_user_id=owner_user_id,
                    visibility=visibility,
                    status=status,
                    tags=["api", "openapi", "operation"],
                    metadata=op_meta,
                    schema_in=schema_in,
                    schema_out=schema_out,
                    auth_profile_id=auth_profile_id,
                    policy_profile_id=policy_profile_id,
                )
                operations_created += 1
            service.link(
                workspace_id=workspace_id,
                parent_capability_id=service_cap["id"],
                child_capability_id=op_cap["id"],
                relation_type="exposes_tool",
                actor_user_id=owner_user_id,
            )
            operations_synced += 1

    stale_disabled = 0
    tools = list_capabilities(workspace_id=workspace_id, capability_type="tool", limit=5000, db_path=db_path)
    for item in tools:
        meta = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
        if meta.get("managed_by") != "openapi_import":
            continue
        if str(meta.get("openapi_api_slug", "")).strip() != api_slug:
            continue
        if str(item.get("key", "")).strip() in seen_keys:
            continue
        if str(item.get("status", "")).strip().lower() == "disabled":
            continue
        service.update(
            item["id"],
            actor_user_id=owner_user_id,
            workspace_id=workspace_id,
            status="disabled",
        )
        stale_disabled += 1

    return {
        "workspace_id": workspace_id,
        "service_capability_id": service_cap["id"],
        "api_title": api_title,
        "operations_synced": operations_synced,
        "operations_created": operations_created,
        "stale_disabled": stale_disabled,
    }
