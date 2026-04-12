from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import parse as urllib_parse


FULL_ACCESS_WARNING = (
    "Full access can launch or hand off to native applications outside the OS sandbox. "
    "Use it only for trusted workflows."
)
SANDBOX_NOTICE = (
    "Sandbox mode previews the desktop action and validates the target, but it does not "
    "control host applications."
)


@dataclass(frozen=True)
class DesktopAdapter:
    id: str
    name: str
    description: str
    sandbox_actions: tuple[str, ...]
    full_access_actions: tuple[str, ...]
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sandbox_actions"] = list(self.sandbox_actions)
        payload["full_access_actions"] = list(self.full_access_actions)
        return payload


ADAPTERS: dict[str, DesktopAdapter] = {
    "generic": DesktopAdapter(
        id="generic",
        name="Generic Native App",
        description="Launch a local app, open a document, or open a URL with the host OS.",
        sandbox_actions=("list_apps", "open_app", "open_document", "open_url"),
        full_access_actions=("open_app", "open_document", "open_url"),
        notes="Use this for arbitrary native applications outside the built-in adapters.",
    ),
    "whatsapp": DesktopAdapter(
        id="whatsapp",
        name="WhatsApp",
        description="Open WhatsApp or pre-fill a WhatsApp chat hand-off.",
        sandbox_actions=("list_apps", "open_app", "open_chat", "open_url"),
        full_access_actions=("open_app", "open_chat", "open_url"),
        notes="Desktop automation opens the app or deep link; it does not use the official WhatsApp Business API.",
    ),
    "telegram": DesktopAdapter(
        id="telegram",
        name="Telegram",
        description="Open Telegram or pre-fill a Telegram chat hand-off.",
        sandbox_actions=("list_apps", "open_app", "open_chat", "open_url"),
        full_access_actions=("open_app", "open_chat", "open_url"),
        notes="Prefer the official Telegram APIs for robust messaging workflows.",
    ),
    "microsoft_365": DesktopAdapter(
        id="microsoft_365",
        name="Microsoft 365",
        description="Open Outlook, Word, Excel, PowerPoint, Teams, or a local Office document.",
        sandbox_actions=("list_apps", "open_app", "open_document", "open_url"),
        full_access_actions=("open_app", "open_document", "open_url"),
        notes="For durable enterprise workflows, prefer Graph/Office APIs over UI automation where possible.",
    ),
}


def normalize_access_mode(value: str | None) -> str:
    normalized = str(value or "sandbox").strip().lower()
    if normalized not in {"sandbox", "full_access"}:
        return "sandbox"
    return normalized


def describe_capability() -> dict[str, Any]:
    return {
        "service": "desktop_automation_broker",
        "default_access_mode": "sandbox",
        "access_modes": ["sandbox", "full_access"],
        "full_access_warning": FULL_ACCESS_WARNING,
        "sandbox_notice": SANDBOX_NOTICE,
        "event_driven_ready": False,
        "event_driven_note": (
            "This broker is the execution lane for future event-driven desktop automation, "
            "but it does not yet include event subscriptions or background triggers."
        ),
        "supported_apps": [adapter.to_dict() for adapter in ADAPTERS.values()],
    }


def contextualize_manifest(base_manifest: dict | None, inputs: dict | None) -> dict:
    manifest = dict(base_manifest or {})
    desktop = dict(manifest.get("desktop", {}) if isinstance(manifest.get("desktop"), dict) else {})
    access_mode = normalize_access_mode((inputs or {}).get("access_mode"))
    app = str((inputs or {}).get("app", "") or "").strip().lower()
    desktop["allow"] = bool(desktop.get("allow", False))
    desktop["access_mode"] = access_mode
    apps = [
        str(item).strip().lower()
        for item in desktop.get("apps", [])
        if str(item).strip()
    ]
    if app:
        if "generic" in apps or app in ADAPTERS:
            desktop["apps"] = [app]
        else:
            desktop["apps"] = apps
    else:
        desktop["apps"] = apps
    desktop["warn_on_full_access"] = bool(desktop.get("warn_on_full_access", True))
    manifest["desktop"] = desktop
    if access_mode == "full_access":
        manifest["requires_approval"] = True
    return manifest


def _runtime_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        try:
            version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            version = ""
        if "microsoft" in version or "wsl" in version:
            return "wsl"
        return "linux"
    return sys.platform


def _quote_query(value: str) -> str:
    return urllib_parse.quote(str(value or ""), safe="")


def _normalize_handle(value: str) -> str:
    return str(value or "").strip().lstrip("@")


def _normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit() or ch == "+")
    return digits


def _coerce_app_name(inputs: dict) -> str:
    for key in ("app_name", "target", "value"):
        candidate = str(inputs.get(key, "") or "").strip()
        if candidate:
            return candidate
    raise ValueError("An app_name is required for generic open_app actions.")


def _coerce_document_path(inputs: dict) -> str:
    document_path = str(inputs.get("document_path", "") or inputs.get("path", "") or "").strip()
    if not document_path:
        raise ValueError("document_path is required for open_document actions.")
    resolved = Path(document_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Document not found: {resolved}")
    return str(resolved)


def _office_app_name(inputs: dict) -> str:
    office_app = str(inputs.get("office_app", "") or "").strip().lower()
    mapping = {
        "outlook": "Microsoft Outlook",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "teams": "Microsoft Teams",
    }
    if office_app in mapping:
        return mapping[office_app]
    target = str(inputs.get("target", "") or "").strip().lower()
    if target in mapping:
        return mapping[target]
    document_path = str(inputs.get("document_path", "") or inputs.get("path", "") or "").strip().lower()
    if document_path.endswith(".doc") or document_path.endswith(".docx"):
        return mapping["word"]
    if document_path.endswith(".xls") or document_path.endswith(".xlsx") or document_path.endswith(".csv"):
        return mapping["excel"]
    if document_path.endswith(".ppt") or document_path.endswith(".pptx"):
        return mapping["powerpoint"]
    return mapping["outlook"]


def _build_plan(inputs: dict) -> dict[str, Any]:
    action = str(inputs.get("action", "list_apps") or "list_apps").strip().lower()
    app = str(inputs.get("app", "generic") or "generic").strip().lower()
    if action == "list_apps":
        return {
            "kind": "info",
            "summary": "List desktop automation adapters",
            "app": app,
            "target": "",
        }
    adapter = ADAPTERS.get(app)
    if not adapter:
        raise ValueError(f"Unsupported desktop automation app: {app}")
    if action == "open_app":
        if app == "microsoft_365":
            app_name = _office_app_name(inputs)
            return {
                "kind": "app",
                "app": app,
                "app_name": app_name,
                "summary": f"Open {app_name}",
                "target": app_name,
            }
        if app == "whatsapp":
            return {
                "kind": "uri",
                "app": app,
                "target": "whatsapp://",
                "summary": "Open WhatsApp",
            }
        if app == "telegram":
            return {
                "kind": "uri",
                "app": app,
                "target": "tg://",
                "summary": "Open Telegram",
            }
        app_name = _coerce_app_name(inputs)
        return {
            "kind": "app",
            "app": app,
            "app_name": app_name,
            "target": app_name,
            "summary": f"Open {app_name}",
        }
    if action == "open_url":
        url = str(inputs.get("url", "") or inputs.get("target", "") or "").strip()
        if not url:
            raise ValueError("url is required for open_url actions.")
        return {
            "kind": "url",
            "app": app,
            "target": url,
            "summary": f"Open URL in {adapter.name if app != 'generic' else 'the host OS'}",
        }
    if action == "open_document":
        document_path = _coerce_document_path(inputs)
        return {
            "kind": "file",
            "app": app,
            "app_name": _office_app_name(inputs) if app == "microsoft_365" else "",
            "target": document_path,
            "summary": f"Open document {Path(document_path).name}",
        }
    if action == "open_chat":
        message = str(inputs.get("message", "") or "").strip()
        if app == "whatsapp":
            phone = _normalize_phone(inputs.get("phone_number", "") or inputs.get("target", "") or "")
            if not phone:
                raise ValueError("phone_number is required for WhatsApp chat actions.")
            target = f"https://wa.me/{phone}"
            if message:
                target += f"?text={_quote_query(message)}"
            return {
                "kind": "url",
                "app": app,
                "target": target,
                "summary": f"Open WhatsApp chat for {phone}",
            }
        if app == "telegram":
            handle = _normalize_handle(inputs.get("handle", "") or inputs.get("target", "") or "")
            if handle:
                target = f"https://t.me/{handle}"
            elif message:
                target = f"tg://msg?text={_quote_query(message)}"
            else:
                raise ValueError("handle or message is required for Telegram chat actions.")
            return {
                "kind": "url",
                "app": app,
                "target": target,
                "summary": f"Open Telegram target {handle or 'message draft'}",
            }
        raise ValueError(f"open_chat is not supported for {adapter.name}")
    raise ValueError(f"Unsupported desktop automation action: {action}")


def _command_preview(plan: dict[str, Any]) -> list[str]:
    runtime = _runtime_platform()
    kind = str(plan.get("kind", "") or "").strip().lower()
    target = str(plan.get("target", "") or "").strip()
    app_name = str(plan.get("app_name", "") or "").strip()
    if runtime in {"windows", "wsl"}:
        launch_target = app_name if kind == "app" and app_name else target
        return ["cmd.exe", "/C", "start", "", launch_target]
    if runtime == "macos":
        if kind == "app" and app_name:
            return ["open", "-a", app_name]
        return ["open", target]
    if kind == "app" and app_name:
        return [app_name]
    return ["xdg-open", target]


def _dispatch_plan(plan: dict[str, Any], *, timeout_seconds: int = 10) -> dict[str, Any]:
    command = _command_preview(plan)
    process = subprocess.Popen(  # noqa: S603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=max(1, int(timeout_seconds or 10)))
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=2)
        raise TimeoutError("Desktop automation dispatch timed out.")
    return {
        "dispatched": process.returncode == 0,
        "returncode": int(process.returncode or 0),
        "stdout": stdout,
        "stderr": stderr,
        "command": command,
    }


def execute_request(inputs: dict | None, *, access_mode: str = "sandbox", timeout_seconds: int = 10) -> dict[str, Any]:
    payload = inputs if isinstance(inputs, dict) else {}
    normalized_mode = normalize_access_mode(access_mode or payload.get("access_mode"))
    plan = _build_plan(payload)
    response = {
        "access_mode": normalized_mode,
        "runtime_platform": _runtime_platform(),
        "warning": FULL_ACCESS_WARNING if normalized_mode == "full_access" else SANDBOX_NOTICE,
        "plan": {
            **plan,
            "command_preview": _command_preview(plan) if plan.get("kind") != "info" else [],
        },
    }
    if str(plan.get("kind", "")).strip().lower() == "info":
        response["supported_apps"] = [adapter.to_dict() for adapter in ADAPTERS.values()]
        response["dispatched"] = False
        response["preview_only"] = normalized_mode != "full_access"
        return response
    if normalized_mode != "full_access":
        response["dispatched"] = False
        response["preview_only"] = True
        return response
    dispatch = _dispatch_plan(plan, timeout_seconds=timeout_seconds)
    response.update(dispatch)
    response["preview_only"] = False
    return response
