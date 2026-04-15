from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_STRICT_REQUIRED_MODES = {"python-skill", "shell-command"}
_SANDBOX_PREFERRED_MODES = {"python-skill", "shell-command", "http-request", "web-search", "desktop-automation"}


@dataclass
class SandboxLaunch:
    command: list[str]
    env: dict[str, str]
    sandbox: dict[str, Any]
    blocked_error: str = ""


def _filesystem_roots(payload: dict, key: str) -> list[str]:
    permissions = payload.get("permissions") if isinstance(payload.get("permissions"), dict) else {}
    filesystem = permissions.get("filesystem") if isinstance(permissions.get("filesystem"), dict) else {}
    values = filesystem.get(key, []) if isinstance(filesystem.get(key, []), list) else []
    roots: list[str] = []
    for item in values:
        normalized = str(item or "").strip()
        if normalized and normalized not in roots:
            roots.append(normalized)
    return roots


def _network_allowed(payload: dict) -> bool:
    permissions = payload.get("permissions") if isinstance(payload.get("permissions"), dict) else {}
    network = permissions.get("network") if isinstance(permissions.get("network"), dict) else {}
    return bool(network.get("allow", False))


def _desktop_access_mode(payload: dict) -> str:
    permissions = payload.get("permissions") if isinstance(payload.get("permissions"), dict) else {}
    desktop = permissions.get("desktop") if isinstance(permissions.get("desktop"), dict) else {}
    return str(desktop.get("access_mode", "sandbox") or "sandbox").strip().lower()


def _sandbox_required(mode: str) -> bool:
    return str(mode or "").strip() in _STRICT_REQUIRED_MODES


def _sandbox_enabled(mode: str) -> bool:
    return str(mode or "").strip() in _SANDBOX_PREFERRED_MODES


def _bubblewrap_binary() -> str:
    return str(shutil.which("bwrap") or "").strip()


def _linux_bubblewrap_supported() -> bool:
    return os.name == "posix" and sys.platform.startswith("linux")


def _install_hint() -> str:
    if _linux_bubblewrap_supported():
        return "Install bubblewrap (for example: sudo apt install bubblewrap) and restart Kendr."
    return "Bubblewrap sandboxing is currently only available on Linux in this runtime."


def describe_runtime_support() -> dict[str, Any]:
    supported = _linux_bubblewrap_supported()
    available = bool(_bubblewrap_binary()) if supported else False
    reason = ""
    if supported and not available:
        reason = "Bubblewrap is not installed, so high-risk extension execution is blocked."
    elif not supported:
        reason = "Bubblewrap sandboxing is not supported on this platform."
    return {
        "provider": "bubblewrap",
        "platform": sys.platform,
        "supported": supported,
        "available": available,
        "reason": reason,
        "install_hint": _install_hint(),
        "required_modes": sorted(_STRICT_REQUIRED_MODES),
        "fallback_modes": sorted(_SANDBOX_PREFERRED_MODES - _STRICT_REQUIRED_MODES),
    }


def extension_host_mode_for_skill(*, skill_type: str = "", catalog_id: str = "") -> str:
    normalized_skill = str(skill_type or "").strip().lower()
    normalized_catalog = str(catalog_id or "").strip().lower()
    if normalized_skill == "python":
        return "python-skill"
    if normalized_skill != "catalog":
        return ""
    if normalized_catalog == "web-search":
        return "web-search"
    if normalized_catalog == "desktop-automation":
        return "desktop-automation"
    return ""


def describe_skill_sandbox(*, skill_type: str = "", catalog_id: str = "") -> dict[str, Any]:
    mode = extension_host_mode_for_skill(skill_type=skill_type, catalog_id=catalog_id)
    if not mode:
        normalized_skill = str(skill_type or "").strip().lower()
        normalized_catalog = str(catalog_id or "").strip().lower()
        if normalized_skill == "prompt":
            return {
                "mode": "in_process",
                "provider": "none",
                "required": False,
                "available": False,
                "reason": "Prompt skills run inside the main runtime and do not use the extension host.",
                "install_hint": "",
            }
        if normalized_skill == "catalog" and normalized_catalog == "pdf-reader":
            return {
                "mode": "in_process",
                "provider": "none",
                "required": False,
                "available": False,
                "reason": "This skill currently runs inside the main runtime and does not have an OS sandbox boundary.",
                "install_hint": "",
            }
        if normalized_skill == "catalog" and normalized_catalog == "desktop-automation":
            return {
                "mode": "configurable",
                "provider": "desktop_automation_broker",
                "required": False,
                "available": True,
                "reason": (
                    "Sandbox mode previews desktop actions without touching host applications. "
                    "Set access_mode=full_access to dispatch to native apps after approval."
                ),
                "install_hint": "",
            }
        return {
            "mode": "process_isolated_only",
            "provider": "none",
            "required": False,
            "available": False,
            "reason": "This skill does not currently use the extension sandbox.",
            "install_hint": "",
        }
    support = describe_runtime_support()
    required = _sandbox_required(mode)
    if mode == "desktop-automation":
        reason = (
            "Sandbox mode previews brokered desktop actions. "
            "Full-access execution dispatches to native apps outside the OS sandbox after approval."
        )
        return {
            "mode": "configurable",
            "provider": "desktop_automation_broker",
            "required": False,
            "available": True,
            "reason": reason,
            "install_hint": support["install_hint"] if not support["available"] else "",
        }
    if support["available"]:
        return {
            "mode": "bubblewrap",
            "provider": "bubblewrap",
            "required": required,
            "available": True,
            "reason": "",
            "install_hint": "",
        }
    mode_name = "blocked" if required else "process_isolated_only"
    if required:
        reason = support["reason"] or "Sandbox support is unavailable for this execution path."
    else:
        reason = support["reason"] or "Sandbox support is unavailable, so this skill falls back to process isolation."
    return {
        "mode": mode_name,
        "provider": "bubblewrap",
        "required": required,
        "available": False,
        "reason": reason,
        "install_hint": support["install_hint"],
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _prepare_code_bundle(launch_root: str) -> str:
    bundle_root = Path(launch_root).expanduser().resolve() / "app"
    package_root = _project_root() / "kendr"
    target_root = bundle_root / "kendr"
    shutil.copytree(
        package_root,
        target_root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    return str(bundle_root)


def _hidden_roots() -> list[str]:
    candidates = [
        "/home",
        "/mnt",
        "/media",
        "/run/user",
        str(Path.home()),
    ]
    roots: list[str] = []
    for item in candidates:
        normalized = str(item or "").strip()
        if not normalized:
            continue
        path = Path(normalized).expanduser()
        if not path.exists():
            continue
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = normalized
        if resolved in roots:
            continue
        if any(resolved.startswith(existing.rstrip("/") + "/") for existing in roots):
            continue
        roots.append(resolved)
    return roots


def _bind_args(flag: str, roots: list[str]) -> list[str]:
    args: list[str] = []
    seen: list[str] = []
    for item in roots:
        normalized = str(item or "").strip()
        if not normalized:
            continue
        try:
            resolved = str(Path(normalized).expanduser().resolve())
        except Exception:
            continue
        if resolved in seen:
            continue
        if not Path(resolved).exists():
            continue
        seen.append(resolved)
        args.extend([flag, resolved, resolved])
    return args


def _sandbox_env(base_env: dict[str, str], payload: dict, *, app_root: str, launch_root: str) -> dict[str, str]:
    env: dict[str, str] = {
        "PATH": str(base_env.get("PATH", "") or "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "LANG": str(base_env.get("LANG", "") or "C.UTF-8"),
        "LC_ALL": str(base_env.get("LC_ALL", "") or "C.UTF-8"),
        "TERM": str(base_env.get("TERM", "") or "dumb"),
        "PYTHONIOENCODING": str(base_env.get("PYTHONIOENCODING", "") or "utf-8"),
        "PYTHONPATH": str(app_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(launch_root),
        "TMPDIR": str(launch_root),
        "TMP": str(launch_root),
        "TEMP": str(launch_root),
    }
    injected = payload.get("injected_env") if isinstance(payload.get("injected_env"), dict) else {}
    for key, value in injected.items():
        normalized_key = str(key or "").strip()
        normalized_value = str(value or "")
        if normalized_key and normalized_value:
            env[normalized_key] = normalized_value
    return env


def _bubblewrap_command(
    *,
    mode: str,
    payload: dict,
    base_command: list[str],
    launch_root: str,
    base_env: dict[str, str],
) -> SandboxLaunch:
    launch_root_resolved = str(Path(launch_root).expanduser().resolve())
    app_root = _prepare_code_bundle(launch_root_resolved)
    read_roots = _filesystem_roots(payload, "read")
    write_roots = _filesystem_roots(payload, "write")
    env = _sandbox_env(base_env, payload, app_root=app_root, launch_root=launch_root_resolved)

    command: list[str] = [
        _bubblewrap_binary(),
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
    ]
    if not _network_allowed(payload):
        command.extend(["--unshare-net"])
    for hidden_root in _hidden_roots():
        command.extend(["--tmpfs", hidden_root])
    command.extend(["--bind", launch_root_resolved, launch_root_resolved])
    command.extend(_bind_args("--ro-bind", read_roots))
    command.extend(_bind_args("--bind", write_roots))
    for key, value in env.items():
        command.extend(["--setenv", key, value])
    command.extend(["--chdir", launch_root_resolved])
    command.extend(base_command)
    return SandboxLaunch(
        command=command,
        env=dict(base_env),
        sandbox={
            "mode": "bubblewrap",
            "provider": "bubblewrap",
            "required": _sandbox_required(mode),
            "available": True,
            "reason": "",
        },
    )


def prepare_extension_host_launch(
    *,
    mode: str,
    payload: dict,
    base_command: list[str],
    base_env: dict[str, str],
    launch_root: str,
) -> SandboxLaunch:
    normalized_mode = str(mode or "").strip()
    if normalized_mode == "desktop-automation" and _desktop_access_mode(payload) == "full_access":
        return SandboxLaunch(
            command=list(base_command),
            env=dict(base_env),
            sandbox={
                "mode": "full_access",
                "provider": "desktop_automation_broker",
                "required": False,
                "available": True,
                "reason": (
                    "Full access was explicitly requested. Native app dispatch runs outside the OS sandbox "
                    "after approval."
                ),
            },
        )
    required = _sandbox_required(normalized_mode)
    enabled = _sandbox_enabled(normalized_mode)
    provider = "bubblewrap"
    if not enabled:
        return SandboxLaunch(
            command=list(base_command),
            env=dict(base_env),
            sandbox={
                "mode": "process_isolated_only",
                "provider": "none",
                "required": False,
                "available": False,
                "reason": "Sandboxing is not enabled for this extension-host mode.",
            },
        )
    if os.name != "posix" or not sys.platform.startswith("linux"):
        reason = "Linux bubblewrap sandboxing is unavailable on this platform."
        mode_name = "blocked" if required else "process_isolated_only"
        return SandboxLaunch(
            command=list(base_command),
            env=dict(base_env),
            sandbox={
                "mode": mode_name,
                "provider": provider,
                "required": required,
                "available": False,
                "reason": reason,
            },
            blocked_error=reason if required else "",
        )
    if not _bubblewrap_binary():
        reason = "Bubblewrap is required for this extension execution path but is not installed."
        mode_name = "blocked" if required else "process_isolated_only"
        return SandboxLaunch(
            command=list(base_command),
            env=dict(base_env),
            sandbox={
                "mode": mode_name,
                "provider": provider,
                "required": required,
                "available": False,
                "reason": reason,
            },
            blocked_error=reason if required else "",
        )
    return _bubblewrap_command(
        mode=normalized_mode,
        payload=payload,
        base_command=base_command,
        launch_root=launch_root,
        base_env=base_env,
    )
