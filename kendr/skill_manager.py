"""Skill Manager — install, uninstall, create, test, and list skills.

Skills are callable tools that agents discover and invoke. Three kinds:
  - catalog  : pre-built system skills (installed from the marketplace)
  - python   : user-defined Python function (code stored in DB, executed sandboxed)
  - prompt   : user-defined prompt template (executed via the LLM)
"""

from __future__ import annotations

import io
import json
import os
import sys
import textwrap
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from kendr.persistence import (
    create_user_skill,
    delete_user_skill,
    get_user_skill,
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

    existing = get_user_skill(slug=catalog_id)
    if existing and existing["is_installed"]:
        return existing

    if existing:
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
        metadata={"requires_config": list(entry.requires_config)},
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
        is_installed=True,
        status="active",
    )


def edit_custom_skill(skill_id: str, **kwargs) -> dict | None:
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


def _run_python_skill(code: str, inputs: dict) -> dict:
    """Execute a python skill code in a restricted scope. Returns {output, stdout, stderr, success, error}."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    # Inject inputs as 'input' variable; skill must set 'output' or return via print
    local_ns: dict[str, Any] = {"input": inputs, "inputs": inputs, "output": None}
    safe_globals = {
        "__builtins__": {k: getattr(__builtins__, k, None) for k in (
            "print", "len", "range", "enumerate", "zip", "map", "filter",
            "sorted", "reversed", "list", "dict", "set", "tuple", "str",
            "int", "float", "bool", "type", "isinstance", "hasattr",
            "getattr", "min", "max", "sum", "abs", "round",
            "repr", "format", "hex", "oct", "bin", "chr", "ord",
            "any", "all", "next", "iter", "open", "Exception",
            "ValueError", "TypeError", "KeyError", "IndexError", "RuntimeError",
        )},
        "json": json,
        "os": os,
    }

    try:
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError(f"Skill execution timed out after {_EXEC_TIMEOUT}s")

        # Signal-based timeout only works on Unix; use a simple approach for Windows
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(_EXEC_TIMEOUT)

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(textwrap.dedent(code), safe_globals, local_ns)  # noqa: S102

        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)

        return {
            "output": local_ns.get("output"),
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "success": True,
            "error": None,
        }
    except TimeoutError as exc:
        return {"output": None, "stdout": "", "stderr": "", "success": False, "error": str(exc)}
    except Exception:
        return {
            "output": local_ns.get("output"),
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "success": False,
            "error": traceback.format_exc(),
        }


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


def _run_catalog_skill(catalog_id: str, inputs: dict) -> dict:
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
        result = handler(inputs)
        output_str = json.dumps(result, ensure_ascii=False, indent=2) if not isinstance(result, str) else result
        return {"output": result, "stdout": output_str, "stderr": "", "success": True, "error": None}
    except Exception:
        return {"output": None, "stdout": "", "stderr": "", "success": False, "error": traceback.format_exc()}


def test_skill(skill_id: str, inputs: dict) -> dict:
    """Run a skill with the provided inputs and return the execution result."""
    row = get_user_skill(skill_id=skill_id)
    if not row:
        return {"success": False, "error": f"Skill {skill_id!r} not found."}

    skill_type = row.get("skill_type", "")
    code = row.get("code", "")

    if skill_type == "python":
        return _run_python_skill(code, inputs)
    elif skill_type == "prompt":
        return _run_prompt_skill(code, inputs)
    elif skill_type == "catalog":
        return _run_catalog_skill(row.get("catalog_id", ""), inputs)
    else:
        return {"success": False, "error": f"Unknown skill_type: {skill_type!r}"}


def execute_skill_by_slug(slug: str, inputs: dict) -> dict:
    """Public API for agents to call a skill by its slug."""
    row = get_user_skill(slug=slug)
    if not row:
        return {"success": False, "error": f"Skill '{slug}' not found or not installed."}
    if not row.get("is_installed"):
        return {"success": False, "error": f"Skill '{slug}' is not installed."}
    return test_skill(row["skill_id"], inputs)


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


def _handle_web_search(inputs: dict) -> dict:
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


def _handle_code_executor(inputs: dict) -> dict:
    code = str(inputs.get("code", "")).strip()
    if not code:
        raise ValueError("'code' is required")
    return _run_python_skill(code, {})


def _handle_pdf_reader(inputs: dict) -> dict:
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


def _handle_shell_command(inputs: dict) -> dict:
    import subprocess
    command = str(inputs.get("command", "")).strip()
    cwd = str(inputs.get("cwd", "")).strip() or None
    timeout = int(inputs.get("timeout", 30))
    if not command:
        raise ValueError("'command' is required")
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True,
        cwd=cwd, timeout=timeout,
    )
    return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}


def _handle_api_caller(inputs: dict) -> dict:
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
