"""
kendr/project_context.py
------------------------
Manages the kendr.md project-context file for each registered project.

kendr.md lives at <project_root>/kendr.md and acts as the persistent memory
store about the project — similar to replit.md, claude.md, etc.  It is:

  • Auto-generated the first time a project is activated (structural scan,
    no LLM call required).
  • Injected into every chat session as system context so the agent
    immediately understands the codebase without asking the user to explain.
  • Updated by agents after meaningful analysis or code changes.
"""

from __future__ import annotations

import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KENDR_MD_FILENAME = "kendr.md"

_IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".next", ".nuxt",
    "coverage", ".cache", "tmp", ".tmp", "logs",
}

_KEY_FILES = [
    "README.md", "README.rst", "README.txt",
    "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "requirements-dev.txt",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", ".env.example", "config.yaml", "config.yml",
    "tsconfig.json", "next.config.js", "next.config.ts",
    "vite.config.ts", "vite.config.js",
    ".env", ".flake8", "mypy.ini", "pytest.ini",
]

_MAX_KEY_FILE_BYTES = 4_000
_MAX_TREE_DEPTH = 4
_MAX_TREE_ENTRIES = 200


# ---------------------------------------------------------------------------
# File tree
# ---------------------------------------------------------------------------

def _file_tree_lines(root: Path, depth: int = 0, counter: list[int] | None = None) -> list[str]:
    if counter is None:
        counter = [0]
    if depth > _MAX_TREE_DEPTH or counter[0] >= _MAX_TREE_ENTRIES:
        return []
    lines: list[str] = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return []
    indent = "  " * depth
    for entry in entries:
        if counter[0] >= _MAX_TREE_ENTRIES:
            lines.append(f"{indent}... (truncated)")
            break
        if entry.name.startswith(".") and entry.name not in {".env", ".env.example"}:
            continue
        if entry.is_dir() and entry.name in _IGNORED_DIRS:
            continue
        counter[0] += 1
        if entry.is_dir():
            lines.append(f"{indent}{entry.name}/")
            lines.extend(_file_tree_lines(entry, depth + 1, counter))
        else:
            size = ""
            try:
                sz = entry.stat().st_size
                if sz >= 1024:
                    size = f" ({sz // 1024}KB)"
            except OSError:
                pass
            lines.append(f"{indent}{entry.name}{size}")
    return lines


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------

def _detect_stack(root: Path) -> str:
    clues: list[str] = []
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        clues.append("Python")
    if (root / "requirements.txt").exists():
        clues.append("Python (pip)")
    if (root / "package.json").exists():
        clues.append("Node.js / JavaScript")
    if (root / "tsconfig.json").exists():
        clues.append("TypeScript")
    if (root / "next.config.js").exists() or (root / "next.config.ts").exists():
        clues.append("Next.js")
    if (root / "vite.config.ts").exists() or (root / "vite.config.js").exists():
        clues.append("Vite")
    if (root / "Cargo.toml").exists():
        clues.append("Rust")
    if (root / "go.mod").exists():
        clues.append("Go")
    if (root / "pom.xml").exists() or (root / "build.gradle").exists():
        clues.append("Java / JVM")
    if (root / "Dockerfile").exists():
        clues.append("Docker")
    if (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists():
        clues.append("Docker Compose")
    if not clues:
        clues.append("Unknown")
    return ", ".join(dict.fromkeys(clues))


# ---------------------------------------------------------------------------
# Generate kendr.md (no LLM — pure structural scan)
# ---------------------------------------------------------------------------

def generate_kendr_md(
    project_root: str,
    project_name: str = "",
    extra_notes: str = "",
) -> str:
    """
    Scan the project and produce a fresh kendr.md string.

    Does NOT require an LLM — it's a fast structural scan that gives the
    agent enough context to start working immediately.
    """
    root = Path(project_root).expanduser().resolve()
    if not root.exists():
        return f"# Project: {project_name or root.name}\n\n> ⚠️ Directory not found: `{root}`\n"

    name = project_name or root.name
    stack = _detect_stack(root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sections: list[str] = []

    # Header
    sections.append(f"# Project: {name}\n")
    sections.append(
        f"_Auto-generated by kendr on {now}. "
        f"Update this file to give the agent permanent context about your project._\n"
    )

    # Summary placeholder — agents will fill this in
    sections.append("## Summary\n")
    sections.append(
        f"**{name}** — {stack} project at `{root}`.\n"
        "(Agents will update this section as they learn about the project.)\n"
    )

    # Tech stack
    sections.append("## Tech Stack\n")
    sections.append(f"{stack}\n")

    # File tree
    sections.append("## File Structure\n")
    sections.append("```\n" + root.name + "/")
    tree_lines = _file_tree_lines(root)
    sections.append("\n".join(tree_lines))
    sections.append("```\n")

    # Key file excerpts
    key_sections: list[str] = []
    for fname in _KEY_FILES:
        fpath = root / fname
        if not fpath.exists() or not fpath.is_file():
            continue
        try:
            raw = fpath.read_bytes()
            if b"\x00" in raw[:512]:
                continue
            text = raw.decode("utf-8", errors="replace")[:_MAX_KEY_FILE_BYTES]
            if len(raw) > _MAX_KEY_FILE_BYTES:
                text += "\n... (truncated)"
        except OSError:
            continue
        key_sections.append(f"### `{fname}`\n\n```\n{text}\n```\n")

    if key_sections:
        sections.append("## Key Files\n")
        sections.extend(key_sections)

    # Architecture notes (empty initially — agents fill this in)
    sections.append("## Architecture Notes\n")
    sections.append(
        "_Agents update this section when they understand the codebase architecture._\n"
    )

    # Agent notes
    sections.append("## Agent Notes\n")
    if extra_notes:
        sections.append(extra_notes + "\n")
    else:
        sections.append("_No notes yet._\n")

    # Instructions for agents
    sections.append("## Agent Instructions\n")
    sections.append(
        textwrap.dedent("""\
        When working on this project:
        - Always read this file at the start of each session.
        - Update the **Summary** and **Architecture Notes** sections when you learn something important.
        - Append discoveries to **Agent Notes** — do NOT erase prior notes.
        - Use `project_root` for all file operations (never hardcode paths).
        - Prefer reading existing code before generating new code.
        - Run tests before marking a task complete.
        """)
    )

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Read / Write
# ---------------------------------------------------------------------------

def kendr_md_path(project_root: str) -> Path:
    return Path(project_root).expanduser().resolve() / KENDR_MD_FILENAME


def read_kendr_md(project_root: str) -> str:
    """Return the contents of kendr.md, or '' if it doesn't exist."""
    path = kendr_md_path(project_root)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def write_kendr_md(project_root: str, content: str) -> Path:
    """Write content to kendr.md and return the path."""
    path = kendr_md_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def ensure_kendr_md(project_root: str, project_name: str = "") -> str:
    """
    Return kendr.md contents, generating the file if it doesn't exist yet.
    This is called automatically when a project is activated.
    """
    existing = read_kendr_md(project_root)
    if existing.strip():
        return existing
    content = generate_kendr_md(project_root, project_name)
    write_kendr_md(project_root, content)
    return content


def append_agent_note(project_root: str, note: str, agent_name: str = "agent") -> None:
    """
    Append a note to the Agent Notes section of kendr.md.
    Safe to call from any agent at any time.
    """
    content = read_kendr_md(project_root)
    if not content:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"\n**[{now}] {agent_name}:** {note.strip()}\n"
    if "## Agent Notes" in content:
        content = content.replace(
            "_No notes yet._\n", "", 1
        )
        # Find the section and append after it
        idx = content.find("## Agent Notes")
        # Find the next ## section after Agent Notes
        next_section = content.find("\n## ", idx + 1)
        if next_section == -1:
            content = content + entry
        else:
            content = content[:next_section] + entry + content[next_section:]
    else:
        content += f"\n## Agent Notes\n{entry}\n"
    write_kendr_md(project_root, content)


def update_summary(project_root: str, summary: str) -> None:
    """Replace the Summary section content in kendr.md."""
    content = read_kendr_md(project_root)
    if not content:
        return
    lines = content.split("\n")
    out: list[str] = []
    in_summary = False
    replaced = False
    for line in lines:
        if line.startswith("## Summary"):
            in_summary = True
            out.append(line)
            continue
        if in_summary and line.startswith("## "):
            if not replaced:
                out.append(summary.strip())
                out.append("")
                replaced = True
            in_summary = False
        if not in_summary:
            out.append(line)
    write_kendr_md(project_root, "\n".join(out))


# ---------------------------------------------------------------------------
# Context blob for injection into agent state
# ---------------------------------------------------------------------------

def get_project_context_blob(project_root: str, project_name: str = "") -> str:
    """
    Return a formatted context string suitable for injection into the agent's
    system context.  Reads kendr.md (generating it if missing), and returns
    it along with a brief header.
    """
    md = ensure_kendr_md(project_root, project_name)
    if not md.strip():
        return ""
    return (
        "=== PROJECT CONTEXT (kendr.md) ===\n"
        f"Project root: {project_root}\n\n"
        f"{md}\n"
        "=== END PROJECT CONTEXT ===\n"
    )
