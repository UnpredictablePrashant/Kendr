"""Skill Manager — install, uninstall, create, test, and list skills.

Skills are callable tools that agents discover and invoke. Three kinds:
  - catalog  : pre-built system skills (installed from the marketplace)
  - python   : user-defined Python function (code stored in DB, executed sandboxed)
  - prompt   : user-defined prompt template (executed via the LLM)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from kendr.extension_permissions import (
    ensure_manifest_approval,
    merge_permissions_into_metadata,
    normalize_approval,
    permission_manifest_from_metadata,
    summarize_permission_manifest,
)
from kendr.persistence import (
    create_user_skill,
    delete_user_skill,
    get_user_skill,
    insert_privileged_audit_event,
    list_user_skills,
    set_skill_installed,
    update_user_skill,
)
from kendr.skill_catalog import CATALOG_BY_ID, list_catalog_skills, catalog_categories


# ---------------------------------------------------------------------------
# Marketplace listing
# ---------------------------------------------------------------------------

def get_marketplace(q: str = "", category: str = "") -> dict:
    """Return catalog skills enriched with their installed state."""
    catalog = list_catalog_skills(category=category, q=q)

    # Map slug → installed row
    installed_rows = {r["slug"]: r for r in list_user_skills(is_installed=True)}

    for item in catalog:
        slug = item["id"]
        installed_row = installed_rows.get(slug)
        item["is_installed"] = installed_row is not None
        item["skill_id"] = installed_row["skill_id"] if installed_row else None
        item["permission_manifest"] = permission_manifest_from_metadata(
            {},
            skill_type="catalog",
            catalog_id=slug,
            cwd=_default_execution_cwd(),
        )

    # Append custom (python/prompt) skills that are installed
    custom = [
        r for r in list_user_skills()
        if r["skill_type"] in ("python", "prompt")
    ]

    return {
        "catalog": catalog,
        "custom": custom,
        "categories": catalog_categories(),
        "installed_count": len(installed_rows) + len([c for c in custom if c["is_installed"]]),
    }


# ---------------------------------------------------------------------------
# Install / Uninstall catalog skill
# ---------------------------------------------------------------------------

def install_catalog_skill(catalog_id: str) -> dict:
    """Install a catalog skill — persists as a user_skill row with is_installed=True."""
    entry = CATALOG_BY_ID.get(catalog_id)
    if not entry:
        raise ValueError(f"No catalog skill with id {catalog_id!r}")

    metadata = merge_permissions_into_metadata(
        {"requires_config": list(entry.requires_config)},
        None,
        skill_type="catalog",
        catalog_id=entry.id,
        cwd=_default_execution_cwd(),
    )

    existing = get_user_skill(slug=catalog_id)
    if existing and existing["is_installed"]:
        updated = update_user_skill(existing["skill_id"], metadata=metadata)
        return updated or existing

    if existing:
        update_user_skill(existing["skill_id"], metadata=metadata)
        set_skill_installed(existing["skill_id"], True)
        return get_user_skill(skill_id=existing["skill_id"])  # type: ignore[return-value]

    return create_user_skill(
        name=entry.name,
        slug=entry.id,
        description=entry.description,
        category=entry.category,
        icon=entry.icon,
        skill_type="catalog",
        catalog_id=entry.id,
        code="",
        input_schema=dict(entry.input_schema),
        output_schema=dict(entry.output_schema),
        tags=list(entry.tags),
        metadata=metadata,
        is_installed=True,
        status="active",
    )


def uninstall_catalog_skill(catalog_id: str) -> bool:
    """Mark a catalog skill as uninstalled (does not delete custom skills)."""
    existing = get_user_skill(slug=catalog_id)
    if not existing:
        return False
    if existing["skill_type"] != "catalog":
        raise ValueError("Use delete_custom_skill for non-catalog skills.")
    set_skill_installed(existing["skill_id"], False)
    return True


# ---------------------------------------------------------------------------
# Create / Update / Delete custom skills
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    import re
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "skill"


def _unique_slug(base: str) -> str:
    slug = base
    n = 1
    while get_user_skill(slug=slug):
        slug = f"{base}-{n}"
        n += 1
    return slug


def create_custom_skill(
    *,
    name: str,
    description: str = "",
    category: str = "Custom",
    icon: str = "⚡",
    skill_type: str,     # 'python' | 'prompt'
    code: str,
    input_schema: dict | None = None,
    output_schema: dict | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
    permissions: dict | None = None,
) -> dict:
    if skill_type not in ("python", "prompt"):
        raise ValueError("skill_type must be 'python' or 'prompt'")
    slug = _unique_slug(_slugify(name))
    return create_user_skill(
        name=name,
        slug=slug,
        description=description,
        category=category,
        icon=icon,
        skill_type=skill_type,
        code=code,
        input_schema=input_schema or {},
        output_schema=output_schema or {},
        tags=tags or [],
        metadata=merge_permissions_into_metadata(
            metadata,
            permissions,
            skill_type=skill_type,
            cwd=_default_execution_cwd(),
        ),
        is_installed=True,
        status="active",
    )


def edit_custom_skill(skill_id: str, **kwargs) -> dict | None:
    if "permissions" in kwargs:
        current = get_user_skill(skill_id=skill_id)
        if current:
            kwargs["metadata"] = merge_permissions_into_metadata(
                kwargs.get("metadata") if isinstance(kwargs.get("metadata"), dict) else current.get("metadata", {}),
                kwargs.pop("permissions"),
                skill_type=str(current.get("skill_type", "") or ""),
                catalog_id=str(current.get("catalog_id", "") or ""),
                cwd=_default_execution_cwd(),
            )
    return update_user_skill(skill_id, **kwargs)


def remove_custom_skill(skill_id: str) -> bool:
    row = get_user_skill(skill_id=skill_id)
    if not row:
        return False
    if row["skill_type"] == "catalog":
        raise ValueError("Use uninstall_catalog_skill for catalog skills.")
    return delete_user_skill(skill_id)


# ---------------------------------------------------------------------------
# Execution / Testing
# ---------------------------------------------------------------------------

_EXEC_TIMEOUT = 10  # seconds


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_execution_cwd() -> str:
    preferred = str(os.getenv("KENDR_WORKING_DIR", "")).strip()
    return preferred or os.getcwd()


def _record_permission_event(skill_label: str, *, action: str, status: str, detail: dict) -> None:
    payload = {
        "event_id": f"skill-permission-{uuid.uuid4().hex}",
        "run_id": "",
        "timestamp": _utc_now(),
        "actor": skill_label,
        "action": action,
        "status": status,
        "detail": detail,
        "prev_hash": "",
        "event_hash": "",
    }
    try:
        insert_privileged_audit_event(payload)
    except Exception:
        pass


def _strip_execution_control(inputs: dict) -> tuple[dict, dict | None]:
    payload = dict(inputs or {})
    approval = payload.pop("_approval", None)
    if approval is None:
        approval = payload.pop("approval", None)
    return payload, approval if isinstance(approval, dict) else None


def _extension_host_env() -> dict[str, str]:
    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TMP",
        "TEMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "TERM",
        "PYTHONIOENCODING",
        "KENDR_HOME",
        "KENDR_DB_PATH",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed and str(value).strip()
    }


def _run_extension_host(mode: str, payload: dict, *, timeout: int) -> dict:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "kendr.extension_host", mode],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=max(1, timeout) + 2,
            env=_extension_host_env(),
        )
    except subprocess.TimeoutExpired:
        return {"output": None, "stdout": "", "stderr": "", "success": False, "error": f"Extension host timed out after {timeout}s"}
    except Exception:
        return {"output": None, "stdout": "", "stderr": "", "success": False, "error": traceback.format_exc()}

    raw_output = completed.stdout.strip()
    if completed.returncode != 0:
        return {
            "output": None,
            "stdout": raw_output,
            "stderr": completed.stderr,
            "success": False,
            "error": completed.stderr or f"Extension host exited with code {completed.returncode}",
        }
    try:
        payload_out = json.loads(raw_output or "{}")
    except Exception:
        return {
            "output": None,
            "stdout": raw_output,
            "stderr": completed.stderr,
            "success": False,
            "error": "Extension host returned invalid JSON",
        }
    return payload_out if isinstance(payload_out, dict) else {
        "output": None,
        "stdout": raw_output,
        "stderr": completed.stderr,
        "success": False,
        "error": "Extension host returned an invalid payload",
    }


def _run_python_skill(code: str, inputs: dict, *, permission_manifest: dict | None = None, approval: dict | None = None, skill_label: str = "skill.python") -> dict:
    """Execute python skill code in an isolated extension-host subprocess."""
    effective_manifest = permission_manifest if isinstance(permission_manifest, dict) else {"requires_approval": False}
    result = _run_extension_host(
        "python-skill",
        {
            "code": code,
            "inputs": inputs,
            "timeout": _EXEC_TIMEOUT,
            "permissions": effective_manifest,
            "approval": normalize_approval(approval),
            "cwd": _default_execution_cwd(),
        },
        timeout=_EXEC_TIMEOUT,
    )
    if not result.get("success", False):
        _record_permission_event(
            skill_label,
            action="python_skill_execution",
            status="blocked" if "approval" in str(result.get("error", "")).lower() or "access denied" in str(result.get("error", "")).lower() else "error",
            detail={
                "error": str(result.get("error", "") or ""),
                "permissions": summarize_permission_manifest(effective_manifest),
            },
        )
    elif effective_manifest.get("requires_approval", False):
        _record_permission_event(
            skill_label,
            action="python_skill_execution",
            status="approved",
            detail={
                "approval": normalize_approval(approval),
                "permissions": summarize_permission_manifest(effective_manifest),
            },
        )
    return result


def _run_prompt_skill(prompt_template: str, inputs: dict) -> dict:
    """Execute a prompt skill via the LLM (best-effort, may not have LLM available)."""
    try:
        # Interpolate {variable} placeholders from inputs
        rendered = prompt_template
        for k, v in inputs.items():
            rendered = rendered.replace(f"{{{k}}}", str(v))

        # Try to call the LLM if available
        try:
            import openai
            client = openai.OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": rendered}],
                max_tokens=1024,
            )
            text = resp.choices[0].message.content or ""
            return {"output": text, "stdout": text, "stderr": "", "success": True, "error": None}
        except Exception as llm_err:
            # Fall back: return the rendered prompt with a note
            return {
                "output": rendered,
                "stdout": f"[LLM unavailable: {llm_err}]\nRendered prompt:\n{rendered}",
                "stderr": "",
                "success": True,
                "error": None,
            }
    except Exception:
        return {"output": None, "stdout": "", "stderr": "", "success": False, "error": traceback.format_exc()}


def _run_catalog_skill(catalog_id: str, inputs: dict, *, permission_manifest: dict | None = None, approval: dict | None = None) -> dict:
    """Dispatch a catalog skill to its built-in handler."""
    handlers = _catalog_handlers()
    handler = handlers.get(catalog_id)
    if not handler:
        return {
            "output": None,
            "stdout": f"Catalog skill '{catalog_id}' has no built-in handler in this environment.",
            "stderr": "",
            "success": False,
            "error": f"No handler registered for catalog skill '{catalog_id}'",
        }
    try:
        result = handler(inputs, permission_manifest=permission_manifest, approval=approval)
        output_str = json.dumps(result, ensure_ascii=False, indent=2) if not isinstance(result, str) else result
        return {"output": result, "stdout": output_str, "stderr": "", "success": True, "error": None}
    except Exception:
        return {"output": None, "stdout": "", "stderr": "", "success": False, "error": traceback.format_exc()}


def test_skill(skill_id: str, inputs: dict, *, approval: dict | None = None) -> dict:
    """Run a skill with the provided inputs and return the execution result."""
    row = get_user_skill(skill_id=skill_id)
    if not row:
        return {"success": False, "error": f"Skill {skill_id!r} not found."}

    skill_type = row.get("skill_type", "")
    code = row.get("code", "")
    safe_inputs, inline_approval = _strip_execution_control(inputs)
    effective_approval = approval if isinstance(approval, dict) else inline_approval
    permission_manifest = permission_manifest_from_metadata(
        row.get("metadata", {}),
        skill_type=str(skill_type or ""),
        catalog_id=str(row.get("catalog_id", "") or ""),
        cwd=_default_execution_cwd(),
    )
    skill_label = f"skill:{row.get('slug', row.get('skill_id', 'unknown'))}"

    if skill_type == "python":
        return _run_python_skill(code, safe_inputs, permission_manifest=permission_manifest, approval=effective_approval, skill_label=skill_label)
    elif skill_type == "prompt":
        try:
            ensure_manifest_approval(permission_manifest, effective_approval, capability="Prompt skill")
        except PermissionError as exc:
            _record_permission_event(
                skill_label,
                action="prompt_skill_execution",
                status="blocked",
                detail={
                    "error": str(exc),
                    "permissions": summarize_permission_manifest(permission_manifest),
                },
            )
            return {"output": None, "stdout": "", "stderr": "", "success": False, "error": str(exc)}
        return _run_prompt_skill(code, safe_inputs)
    elif skill_type == "catalog":
        return _run_catalog_skill(
            row.get("catalog_id", ""),
            safe_inputs,
            permission_manifest=permission_manifest,
            approval=effective_approval,
        )
    else:
        return {"success": False, "error": f"Unknown skill_type: {skill_type!r}"}


def execute_skill_by_slug(slug: str, inputs: dict, *, approval: dict | None = None) -> dict:
    """Public API for agents to call a skill by its slug."""
    row = get_user_skill(slug=slug)
    if not row:
        return {"success": False, "error": f"Skill '{slug}' not found or not installed."}
    if not row.get("is_installed"):
        return {"success": False, "error": f"Skill '{slug}' is not installed."}
    return test_skill(row["skill_id"], inputs, approval=approval)


# ---------------------------------------------------------------------------
# Built-in catalog handlers
# ---------------------------------------------------------------------------

def _catalog_handlers() -> dict[str, Any]:
    """Return a dict of catalog_id → handler function (lazily built)."""
    return {
        "web-search": _handle_web_search,
        "code-executor": _handle_code_executor,
        "pdf-reader": _handle_pdf_reader,
        "shell-command": _handle_shell_command,
        "api-caller": _handle_api_caller,
    }


def _handle_web_search(inputs: dict, **_kwargs) -> dict:
    query = str(inputs.get("query", "")).strip()
    num_results = int(inputs.get("num_results", 5))
    if not query:
        raise ValueError("'query' is required")
    try:
        import requests
        # DuckDuckGo instant answer API (no key required)
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": 1},
            timeout=10,
        )
        data = r.json()
        results = []
        for topic in (data.get("RelatedTopics") or [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({"title": topic.get("Text", ""), "url": topic.get("FirstURL", ""), "snippet": topic.get("Text", "")})
        return {"query": query, "results": results}
    except ImportError:
        return {"query": query, "results": [], "error": "requests library not installed"}


def _handle_code_executor(inputs: dict, *, permission_manifest: dict | None = None, approval: dict | None = None) -> dict:
    code = str(inputs.get("code", "")).strip()
    if not code:
        raise ValueError("'code' is required")
    return _run_python_skill(
        code,
        {},
        permission_manifest=permission_manifest,
        approval=approval,
        skill_label="catalog:code-executor",
    )


def _handle_pdf_reader(inputs: dict, **_kwargs) -> dict:
    file_path = str(inputs.get("file_path", "")).strip()
    if not file_path or not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path!r}")
    try:
        import pypdf
        reader = pypdf.PdfReader(file_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return {"text": text, "page_count": len(reader.pages)}
    except ImportError:
        return {"text": "", "page_count": 0, "error": "pypdf not installed. Run: pip install pypdf"}


def _handle_shell_command(inputs: dict, *, permission_manifest: dict | None = None, approval: dict | None = None) -> dict:
    command = str(inputs.get("command", "")).strip()
    cwd = str(inputs.get("cwd", "")).strip() or None
    timeout = int(inputs.get("timeout", 30))
    if not command:
        raise ValueError("'command' is required")
    result = _run_extension_host(
        "shell-command",
        {
            "command": command,
            "cwd": cwd,
            "timeout": timeout,
            "permissions": permission_manifest or {},
            "approval": normalize_approval(approval),
        },
        timeout=timeout,
    )
    if not result.get("success"):
        _record_permission_event(
            "catalog:shell-command",
            action="shell_command_execution",
            status="blocked" if "approval" in str(result.get("error", "")).lower() or "disabled" in str(result.get("error", "")).lower() or "outside the allowed scope" in str(result.get("error", "")).lower() else "error",
            detail={
                "command": command,
                "cwd": cwd or _default_execution_cwd(),
                "error": str(result.get("error", "") or ""),
                "permissions": summarize_permission_manifest(permission_manifest or {}),
            },
        )
        raise RuntimeError(str(result.get("error", "Shell command execution failed")))
    if permission_manifest and permission_manifest.get("requires_approval", False):
        _record_permission_event(
            "catalog:shell-command",
            action="shell_command_execution",
            status="approved",
            detail={
                "command": command,
                "cwd": cwd or _default_execution_cwd(),
                "approval": normalize_approval(approval),
                "permissions": summarize_permission_manifest(permission_manifest),
            },
        )
    output = result.get("output")
    return output if isinstance(output, dict) else {"stdout": "", "stderr": "", "returncode": 1}


def _handle_api_caller(inputs: dict, **_kwargs) -> dict:
    url = str(inputs.get("url", "")).strip()
    method = str(inputs.get("method", "GET")).upper()
    headers = dict(inputs.get("headers") or {})
    body = inputs.get("body")
    if not url:
        raise ValueError("'url' is required")
    try:
        import requests
        resp = requests.request(method, url, headers=headers, json=body, timeout=15)
        try:
            body_data = resp.json()
        except Exception:
            body_data = resp.text
        return {"status_code": resp.status_code, "body": body_data, "headers": dict(resp.headers)}
    except ImportError:
        return {"status_code": 0, "body": None, "error": "requests library not installed"}
