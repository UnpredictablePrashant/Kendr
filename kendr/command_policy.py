from __future__ import annotations

import re
from pathlib import Path


_DESTRUCTIVE_COMMAND_HINTS = [
    "rm -rf",
    "rm -fr",
    "mkfs",
    "dd if=",
    "shutdown",
    "reboot",
    "halt",
    "del /f",
    "rd /s /q",
    "format ",
    "diskpart",
    "userdel ",
    "drop database",
    "truncate table",
]

_MUTATING_COMMAND_HINTS = [
    "rm ",
    "mv ",
    "cp ",
    "mkdir ",
    "rmdir ",
    "touch ",
    "sed -i",
    "tee ",
    "apt-get install",
    "apt install",
    "apt-get update",
    "apt-get upgrade",
    "yum install",
    "dnf install",
    "pip install",
    "pip3 install",
    "npm install",
    "npm i ",
    "yarn add",
    "pnpm add",
    "brew install",
    "brew update",
    "brew upgrade",
    "choco install",
    "winget install",
    "scoop install",
    "cargo install",
    "go install",
    "pipx install",
    "conda install",
    "snap install",
    "flatpak install",
    "gem install",
    "composer require",
    "docker pull",
    "docker run",
    "docker build",
    "docker-compose up",
    "docker compose up",
    "ollama pull",
    "ollama run",
    "ollama serve",
    "systemctl start",
    "systemctl stop",
    "systemctl enable",
    "systemctl restart",
    "service start",
    "service stop",
    "service restart",
    "git commit",
    "git push",
    "git clone",
    "git pull",
    "chmod ",
    "chown ",
    "ln -s",
    "ln -f",
    "echo ",
    "cat >",
    "write_file",
]


def classify_command(command: str) -> dict:
    lowered = str(command or "").lower()
    root_requested = "sudo " in lowered or lowered.startswith("sudo")
    destructive = any(hint in lowered for hint in _DESTRUCTIVE_COMMAND_HINTS)
    mutating = destructive or any(hint in lowered for hint in _MUTATING_COMMAND_HINTS)
    networking = any(hint in lowered for hint in ["curl ", "wget ", "invoke-webrequest", "http://", "https://", "ssh "])
    return {
        "root_requested": root_requested,
        "destructive": destructive,
        "mutating": mutating,
        "networking": networking,
    }


def extract_path_references(command: str) -> list[str]:
    text = str(command or "")
    refs: set[str] = set()
    unix_matches = re.findall(r"(?:^|\s)(/[A-Za-z0-9._\-/]+)", text)
    win_matches = re.findall(r"([A-Za-z]:\\[^\s\"']+)", text)
    for item in unix_matches + win_matches:
        refs.add(item.strip())
    return sorted(refs)


def path_allowed(path_value: str, allowed_roots: list[str]) -> bool:
    if not allowed_roots:
        return True
    try:
        path_obj = Path(path_value).expanduser().resolve()
    except Exception:
        return False
    for root in allowed_roots:
        try:
            root_obj = Path(root).expanduser().resolve()
        except Exception:
            continue
        if path_obj == root_obj or root_obj in path_obj.parents:
            return True
    return False


def ensure_command_allowed(command: str, working_directory: str, policy: dict) -> None:
    classification = classify_command(command)
    auto_approve = policy.get("auto_approve", False)

    if policy.get("require_approvals", True):
        if auto_approve:
            if not policy.get("approval_note", ""):
                raise PermissionError("Shell automation mode active but approval_note is missing.")
        else:
            if not policy.get("approved", False) or not policy.get("approval_note", ""):
                raise PermissionError(
                    "approval_required: Shell execution requires explicit approval. "
                    "Enable Shell Automation mode in the chat header, or pass "
                    "privileged_approved=True and a privileged_approval_note."
                )

    if policy.get("read_only", False) and classification["mutating"]:
        raise PermissionError("Read-only mode is active — mutating commands are blocked.")
    if classification["root_requested"] and not policy.get("allow_root", False):
        raise PermissionError(
            "Command requests root (sudo) escalation but allow_root is false. "
            "Set KENDR_ALLOW_ROOT=true or privileged_allow_root=true to enable."
        )
    if classification["destructive"] and not policy.get("allow_destructive", False):
        raise PermissionError(
            "Destructive command detected and blocked. "
            "Set KENDR_ALLOW_DESTRUCTIVE=true or privileged_allow_destructive=true to enable."
        )
    if not path_allowed(working_directory, policy.get("allowed_paths", [])):
        raise PermissionError("Working directory is outside the allowed path scope.")
    for ref in extract_path_references(command):
        if not path_allowed(ref, policy.get("allowed_paths", [])):
            raise PermissionError(f"Command references a path outside the allowed scope: {ref}")
