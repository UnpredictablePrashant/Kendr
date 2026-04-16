from __future__ import annotations

from datetime import datetime, timezone
import os
import re
from pathlib import Path
from typing import Any, Mapping

from tasks.research_infra import LOCAL_DRIVE_SUPPORTED_EXTENSIONS, chunk_text, search_memory, upsert_memory_records


DEFAULT_EXTENSION_HANDLER_REGISTRY: dict[str, str] = {
    ".txt": "document_ingestion_agent",
    ".md": "document_ingestion_agent",
    ".json": "document_ingestion_agent",
    ".html": "document_ingestion_agent",
    ".htm": "document_ingestion_agent",
    ".xml": "document_ingestion_agent",
    ".yaml": "document_ingestion_agent",
    ".yml": "document_ingestion_agent",
    ".toml": "document_ingestion_agent",
    ".ini": "document_ingestion_agent",
    ".cfg": "document_ingestion_agent",
    ".conf": "document_ingestion_agent",
    ".env": "document_ingestion_agent",
    ".properties": "document_ingestion_agent",
    ".sql": "document_ingestion_agent",
    ".csv": "document_ingestion_agent",
    ".pdf": "document_ingestion_agent",
    ".doc": "document_ingestion_agent",
    ".docx": "document_ingestion_agent",
    ".xls": "document_ingestion_agent",
    ".xlsx": "excel_agent",
    ".xlsm": "excel_agent",
    ".ppt": "document_ingestion_agent",
    ".pptx": "document_ingestion_agent",
    ".pptm": "document_ingestion_agent",
    ".py": "document_ingestion_agent",
    ".js": "document_ingestion_agent",
    ".jsx": "document_ingestion_agent",
    ".ts": "document_ingestion_agent",
    ".tsx": "document_ingestion_agent",
    ".java": "document_ingestion_agent",
    ".go": "document_ingestion_agent",
    ".rs": "document_ingestion_agent",
    ".c": "document_ingestion_agent",
    ".cc": "document_ingestion_agent",
    ".cpp": "document_ingestion_agent",
    ".h": "document_ingestion_agent",
    ".hpp": "document_ingestion_agent",
    ".cs": "document_ingestion_agent",
    ".rb": "document_ingestion_agent",
    ".php": "document_ingestion_agent",
    ".swift": "document_ingestion_agent",
    ".kt": "document_ingestion_agent",
    ".kts": "document_ingestion_agent",
    ".scala": "document_ingestion_agent",
    ".sh": "document_ingestion_agent",
    ".bash": "document_ingestion_agent",
    ".zsh": "document_ingestion_agent",
    ".ps1": "document_ingestion_agent",
    ".bat": "document_ingestion_agent",
    ".tf": "document_ingestion_agent",
    ".tfvars": "document_ingestion_agent",
    ".gradle": "document_ingestion_agent",
    ".png": "ocr_agent",
    ".jpg": "ocr_agent",
    ".jpeg": "ocr_agent",
    ".bmp": "ocr_agent",
    ".gif": "ocr_agent",
    ".webp": "ocr_agent",
    ".tif": "ocr_agent",
    ".tiff": "ocr_agent",
}

_JUNK_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    "target",
    "tmp",
    "temp",
    "vendor",
    "site-packages",
}

_LOW_SIGNAL_FILENAMES = {
    "readme",
    "changelog",
    "history",
    "license",
    "notice",
    "package",
    "package-lock",
    "yarn.lock",
    "pnpm-lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "package_support",
}

_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php",
    ".swift", ".kt", ".kts", ".scala",
}
_CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".properties", ".xml", ".tf", ".tfvars", ".gradle", ".sh", ".bash",
    ".zsh", ".ps1", ".bat",
}
_SPREADSHEET_EXTENSIONS = {".csv", ".xls", ".xlsx", ".xlsm"}
_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".html", ".htm"}
_PRESENTATION_EXTENSIONS = {".ppt", ".pptx", ".pptm"}

_CODE_OBJECTIVE_MARKERS = {
    "code", "repository", "repo", "source", "implementation", "bug", "debug",
    "api", "service", "module", "class", "function", "architecture", "stack",
    "python", "javascript", "typescript", "java", "golang", "go", "rust",
    "react", "node", "backend", "frontend", "sql", "config",
}
_DATA_OBJECTIVE_MARKERS = {
    "spreadsheet", "excel", "xlsx", "xls", "csv", "financial", "revenue",
    "budget", "forecast", "table", "model", "analysis", "metrics", "numbers",
}
_PRESENTATION_OBJECTIVE_MARKERS = {
    "deck", "slides", "presentation", "ppt", "pptx", "briefing",
}
_DOCUMENT_OBJECTIVE_MARKERS = {
    "report", "document", "proposal", "policy", "contract", "memo", "research",
    "case study", "whitepaper", "doc", "docx", "pdf",
}

_HIGH_SIGNAL_PATH_MARKERS = {
    "abstract",
    "analysis",
    "architecture",
    "brief",
    "business",
    "conclusion",
    "deck",
    "design",
    "diagram",
    "executive",
    "findings",
    "forecast",
    "overview",
    "plan",
    "policy",
    "presentation",
    "proposal",
    "report",
    "requirements",
    "results",
    "roadmap",
    "slides",
    "spec",
    "strategy",
    "summary",
    "whitepaper",
}

_GENERATED_ARTIFACT_MARKERS = {
    "agent_work_notes",
    "coverage_report",
    "evidence_bank",
    "execution.log",
    "local_drive_doc_summary",
    "local_drive_result",
    "quality_report",
    "source_ledger",
}


def _tokenize_objective(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_+-]{3,}", str(text or "").lower()) if token}


def _objective_profile(objective: str) -> dict[str, bool]:
    normalized = str(objective or "").lower()
    tokens = _tokenize_objective(normalized)
    return {
        "code": bool(tokens & _CODE_OBJECTIVE_MARKERS),
        "data": bool(tokens & _DATA_OBJECTIVE_MARKERS),
        "presentation": bool(tokens & _PRESENTATION_OBJECTIVE_MARKERS),
        "document": bool(tokens & _DOCUMENT_OBJECTIVE_MARKERS) or not bool(tokens & _CODE_OBJECTIVE_MARKERS),
    }


def _skip_directory_name(name: str) -> bool:
    return str(name or "").strip().lower() in _JUNK_DIRECTORY_NAMES


def _path_signal_tokens(path: str) -> set[str]:
    return _tokenize_objective(str(path or "").replace("\\", "/"))


def _priority_bucket(extension: str, profile: Mapping[str, bool]) -> str:
    if extension in _SPREADSHEET_EXTENSIONS:
        return "spreadsheet"
    if extension in _PRESENTATION_EXTENSIONS:
        return "presentation"
    if extension in _DOCUMENT_EXTENSIONS:
        return "document"
    if extension in _CODE_EXTENSIONS:
        return "code"
    if extension in _CONFIG_EXTENSIONS:
        return "config"
    return "other"


def _source_family(extension: str) -> str:
    if extension in _DOCUMENT_EXTENSIONS:
        return "document"
    if extension in _PRESENTATION_EXTENSIONS:
        return "presentation"
    if extension in _SPREADSHEET_EXTENSIONS:
        return "spreadsheet"
    if extension in _CODE_EXTENSIONS:
        return "code"
    if extension in _CONFIG_EXTENSIONS:
        return "config"
    if extension in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}:
        return "image"
    return "other"


def _preferred_extension_rank(extension: str, strategy: Mapping[str, Any]) -> int:
    preferred_extensions = strategy.get("preferred_extensions", []) if isinstance(strategy.get("preferred_extensions"), list) else []
    try:
        return preferred_extensions.index(extension)
    except ValueError:
        return -1


def _priority_score(
    entry: Mapping[str, Any],
    objective: str,
    *,
    source_strategy: Mapping[str, Any] | None = None,
) -> tuple[int, str, list[str], list[str]]:
    extension = str(entry.get("extension", "") or "").lower()
    name = str(entry.get("name", "") or "").strip().lower()
    stem = Path(name).stem.lower() if name else ""
    path_tokens = _path_signal_tokens(str(entry.get("path", "") or ""))
    objective_tokens = _tokenize_objective(objective)
    profile = _objective_profile(objective)
    bucket = _priority_bucket(extension, profile)
    strategy = source_strategy if isinstance(source_strategy, Mapping) else {}
    boosts: list[str] = []
    penalties: list[str] = []

    if bucket == "spreadsheet":
        score = 96 if profile["data"] else 84
        boosts.append("tabular evidence favored")
    elif bucket == "presentation":
        score = 96 if profile["presentation"] else 86
        boosts.append("slides can surface summary evidence fast")
    elif bucket == "document":
        score = 88 if profile["document"] else 62
        boosts.append("documents usually carry primary narrative evidence")
    elif bucket == "code":
        score = 98 if profile["code"] else 34
        if profile["code"]:
            boosts.append("code understanding requested")
    elif bucket == "config":
        score = 86 if profile["code"] else 40
        if profile["code"]:
            boosts.append("config can explain runtime behavior")
    else:
        score = 28

    if profile["code"] and extension in _DOCUMENT_EXTENSIONS:
        score -= 16
        penalties.append("document penalized because repository/code evidence is primary")
    if profile["data"] and extension in _CODE_EXTENSIONS:
        score -= 18
        penalties.append("code penalized because numeric evidence matters more")
    if profile["presentation"] and extension in _CODE_EXTENSIONS:
        score -= 20
        penalties.append("code penalized because slide evidence matters more")

    if stem in _LOW_SIGNAL_FILENAMES or name in _LOW_SIGNAL_FILENAMES:
        score -= 38
        penalties.append("boilerplate filename")
    if "test" in path_tokens or "fixture" in path_tokens or "example" in path_tokens:
        score -= 12
        penalties.append("test/example content")

    if any(marker in str(entry.get("path", "") or "").lower() for marker in _GENERATED_ARTIFACT_MARKERS):
        score -= 64
        penalties.append("generated research artifact")

    high_signal_markers = sorted(path_tokens & _HIGH_SIGNAL_PATH_MARKERS)
    if high_signal_markers:
        score += min(20, 5 * len(high_signal_markers))
        boosts.append(f"high-signal filename markers: {', '.join(high_signal_markers[:3])}")

    matched_terms = objective_tokens & path_tokens
    if matched_terms:
        score += min(18, 6 * len(matched_terms))
        boosts.append(f"matched objective terms: {', '.join(sorted(matched_terms)[:3])}")

    preferred_rank = _preferred_extension_rank(extension, strategy)
    if preferred_rank >= 0:
        preference_boost = max(0, 14 - preferred_rank)
        if preference_boost:
            score += preference_boost
            boosts.append("preferred extension for this research strategy")

    size_bytes = int(entry.get("size_bytes", 0) or 0)
    if size_bytes < 256:
        score -= 20
        penalties.append("very small file")
    elif size_bytes < 1024:
        score -= 8
        penalties.append("small file")
    elif size_bytes <= 10_000_000:
        score += 6
        boosts.append("substantive file size")
    elif size_bytes > 100_000_000:
        score -= 8
        penalties.append("very large file may be noisy")

    depth = int(entry.get("depth", 0) or 0)
    score -= min(10, max(0, depth - 2))
    if depth > 2:
        penalties.append("deeply nested path")
    if not bool(entry.get("readable", True)):
        score -= 1000
        penalties.append("not readable")
    return score, bucket, boosts, penalties


def _compose_selection_reason(family: str, strategy_note: str, boosts: list[str]) -> str:
    details = [str(strategy_note or "").strip()] if str(strategy_note or "").strip() else []
    for item in boosts[:2]:
        if item and item not in details:
            details.append(item)
    return " ".join(details).strip()


def _compose_skip_reason(reason: str, family_note: str, penalties: list[str]) -> str:
    prefix = {
        "family_budget_exhausted": "Skipped because the family budget filled before this file.",
        "deprioritized_by_ranking": "Skipped because stronger evidence ranked higher.",
        "unsupported_extension": "Skipped because this extension is not supported.",
    }.get(reason, "")
    details = [prefix] if prefix else []
    if str(family_note or "").strip():
        details.append(str(family_note or "").strip())
    for item in penalties[:2]:
        if item:
            details.append(f"Signal: {item}.")
    return " ".join(part for part in details if part).strip()


def _preselection_skip_detail(path: Path) -> str:
    lowered = str(path).lower()
    stem = path.stem.lower()
    if any(marker in lowered for marker in _GENERATED_ARTIFACT_MARKERS):
        return "Skipped because this looks like a generated research artifact, not primary evidence."
    if stem in _LOW_SIGNAL_FILENAMES or path.name.lower() in _LOW_SIGNAL_FILENAMES:
        return "Skipped because this filename looks like low-signal boilerplate."
    return ""


def extension_handler_registry(
    overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    registry = dict(DEFAULT_EXTENSION_HANDLER_REGISTRY)
    if not isinstance(overrides, Mapping):
        return registry
    for raw_extension, raw_handler in overrides.items():
        extension = f".{str(raw_extension or '').strip().lower().lstrip('.')}"
        handler = str(raw_handler or "").strip()
        if not extension or extension == "." or not handler:
            continue
        registry[extension] = handler
    return registry


def route_files_by_handler(
    file_paths: list[str],
    *,
    registry: Mapping[str, str] | None = None,
    default_handler: str = "document_ingestion_agent",
) -> dict[str, list[str]]:
    selected_registry = extension_handler_registry(registry)
    routes: dict[str, list[str]] = {}
    for raw_path in file_paths or []:
        path = str(raw_path or "").strip()
        if not path:
            continue
        extension = Path(path).suffix.lower()
        handler = selected_registry.get(extension, default_handler)
        if not handler:
            continue
        routes.setdefault(handler, []).append(path)
    return routes


def unknown_extensions_from_manifest(
    manifest: Mapping[str, Any] | None,
    *,
    registry: Mapping[str, str] | None = None,
) -> list[str]:
    selected_registry = extension_handler_registry(registry)
    unknown: set[str] = set()
    if not isinstance(manifest, Mapping):
        return []
    files = manifest.get("files", [])
    if not isinstance(files, list):
        return []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        extension = str(item.get("extension", "") or "").strip().lower()
        if extension and extension not in selected_registry:
            unknown.add(extension)
    return sorted(unknown)


def resolve_paths(raw_paths: str | list[str] | None, working_directory: str | None = None) -> list[str]:
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    results = []
    for raw_path in raw_paths or []:
        candidate = str(raw_path or "").strip()
        if not candidate:
            continue
        windows_drive_match = re.match(r"^([a-zA-Z]):[\\/](.*)$", candidate)
        if windows_drive_match:
            drive = windows_drive_match.group(1).lower()
            tail = windows_drive_match.group(2).replace("\\", "/")
            wsl_path = Path(f"/mnt/{drive}/{tail}")
            path = wsl_path if wsl_path.exists() else Path(candidate)
        else:
            path = Path(candidate)
        if not path.is_absolute():
            path = Path(working_directory or ".").resolve() / path
        results.append(str(path))
    return results


def normalize_extension_set(raw_extensions: str | list[str] | None) -> set[str]:
    if isinstance(raw_extensions, str):
        items = [item.strip() for item in raw_extensions.split(",")]
    elif isinstance(raw_extensions, list):
        items = [str(item).strip() for item in raw_extensions]
    else:
        items = []
    normalized = {f".{item.lower().lstrip('.')}" for item in items if item}
    return normalized or set(LOCAL_DRIVE_SUPPORTED_EXTENSIONS)


def discover_local_drive_files(
    roots: list[str],
    *,
    recursive: bool,
    include_hidden: bool,
    max_files: int,
    allowed_extensions: set[str],
    objective: str = "",
) -> list[str]:
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root_item in roots:
        root = Path(root_item).expanduser().resolve()
        candidates = []
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            iterator = root.rglob("*") if recursive else root.glob("*")
            candidates = [path for path in iterator if path.is_file()]
        for path in sorted(candidates):
            if path in seen:
                continue
            if not include_hidden and any(part.startswith(".") for part in path.parts):
                continue
            seen.add(path)
            entries.append(
                _manifest_entry(
                    path,
                    root=root.parent if root.is_file() else root,
                    entry_type="file",
                    selected_for_processing=False,
                    exclusion_reason="" if path.suffix.lower() in allowed_extensions else "unsupported_extension",
                )
            )
    ranked = [
        item
        for item in entries
        if str(item.get("extension", "") or "").lower() in allowed_extensions
    ]
    ranked.sort(
        key=lambda item: (
            -_priority_score(item, objective)[0],
            str(item.get("name", "")).lower(),
            str(item.get("path", "")).lower(),
        )
    )
    return [str(item.get("path", "")).strip() for item in ranked[:max_files] if str(item.get("path", "")).strip()]


def _is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _iso_timestamp(value: float) -> str:
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    except Exception:
        return ""


def _relative_path(root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(root)
        text = str(relative).replace("\\", "/")
        return text or "."
    except Exception:
        return path.name or str(path)


def _manifest_entry(
    path: Path,
    *,
    root: Path,
    entry_type: str,
    selected_for_processing: bool | None = None,
    exclusion_reason: str = "",
    selection_reason: str = "",
    skip_reason_detail: str = "",
) -> dict[str, Any]:
    stat = path.stat()
    relative_path = _relative_path(root, path)
    extension = path.suffix.lower() if path.is_file() else ""
    return {
        "path": str(path),
        "root": str(root),
        "relative_path": relative_path,
        "name": path.name or str(path),
        "entry_type": entry_type,
        "depth": 0 if relative_path == "." else len(Path(relative_path).parts),
        "extension": extension,
        "source_family": _source_family(extension) if path.is_file() else "",
        "size_bytes": int(stat.st_size) if path.is_file() else 0,
        "modified_at": _iso_timestamp(float(stat.st_mtime)),
        "created_at": _iso_timestamp(float(stat.st_ctime)),
        "is_hidden": _is_hidden_path(path),
        "readable": bool(os.access(path, os.R_OK)),
        "selected_for_processing": selected_for_processing,
        "exclusion_reason": exclusion_reason,
        "selection_reason": selection_reason,
        "skip_reason_detail": skip_reason_detail,
    }


def scan_local_drive_tree(
    roots: list[str],
    *,
    recursive: bool,
    include_hidden: bool,
    max_files: int,
    allowed_extensions: set[str],
    objective: str = "",
    source_strategy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    selected_files: list[str] = []
    seen: set[str] = set()
    truncated = False

    def _record(entry: dict[str, Any]) -> None:
        path_key = str(entry.get("path", "")).strip()
        if not path_key or path_key in seen:
            return
        seen.add(path_key)
        entries.append(entry)
        if entry.get("entry_type") == "directory":
            folders.append(entry)
        elif entry.get("entry_type") == "file":
            files.append(entry)

    def _record_file(path: Path, *, root: Path) -> None:
        suffix = path.suffix.lower()
        exclusion_reason = "" if suffix in allowed_extensions else "unsupported_extension"
        _record(
            _manifest_entry(
                path,
                root=root,
                entry_type="file",
                selected_for_processing=False,
                exclusion_reason=exclusion_reason,
                skip_reason_detail=_preselection_skip_detail(path) if exclusion_reason else "",
            )
        )

    for root_item in roots:
        root = Path(root_item).expanduser().resolve()
        if not root.exists():
            continue
        if root.is_file():
            if include_hidden or not _is_hidden_path(root):
                _record_file(root, root=root.parent if root.parent.exists() else root)
            continue
        if not root.is_dir():
            continue

        _record(_manifest_entry(root, root=root, entry_type="directory"))

        if recursive:
            for current_root, dirnames, filenames in os.walk(root, topdown=True):
                current_path = Path(current_root)
                dirnames.sort()
                filenames.sort()
                if not include_hidden:
                    dirnames[:] = [name for name in dirnames if not name.startswith(".")]
                    filenames = [name for name in filenames if not name.startswith(".")]
                dirnames[:] = [name for name in dirnames if not _skip_directory_name(name)]
                for dirname in dirnames:
                    dir_path = current_path / dirname
                    _record(_manifest_entry(dir_path, root=root, entry_type="directory"))
                for filename in filenames:
                    file_path = current_path / filename
                    _record_file(file_path, root=root)
        else:
            children = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
            for child in children:
                if not include_hidden and child.name.startswith("."):
                    continue
                if child.is_dir():
                    if _skip_directory_name(child.name):
                        continue
                    _record(_manifest_entry(child, root=root, entry_type="directory"))
                elif child.is_file():
                    _record_file(child, root=root)

    selectable_files = [
        item
        for item in files
        if str(item.get("extension", "") or "").lower() in allowed_extensions and bool(item.get("readable", True))
    ]
    ranked_files: list[dict[str, Any]] = []
    for item in selectable_files:
        score, bucket, boosts, penalties = _priority_score(item, objective, source_strategy=source_strategy)
        item["priority_score"] = score
        item["priority_bucket"] = bucket
        item["priority_boosts"] = boosts
        item["priority_penalties"] = penalties
        ranked_files.append(item)
    ranked_files.sort(
        key=lambda item: (
            -int(item.get("priority_score", 0) or 0),
            str(item.get("name", "")).lower(),
            str(item.get("path", "")).lower(),
        )
    )
    selected_set: set[str] = set()
    strategy = source_strategy if isinstance(source_strategy, Mapping) else {}
    family_budgets = strategy.get("family_budgets", {}) if isinstance(strategy.get("family_budgets", {}), Mapping) else {}
    selection_notes = strategy.get("selection_notes", {}) if isinstance(strategy.get("selection_notes", {}), Mapping) else {}
    skip_notes = strategy.get("skip_notes", {}) if isinstance(strategy.get("skip_notes", {}), Mapping) else {}
    family_counts: dict[str, int] = {}
    for rank, item in enumerate(ranked_files, start=1):
        path_value = str(item.get("path", "")).strip()
        item["selection_rank"] = rank
        family = str(item.get("source_family", "") or _source_family(str(item.get("extension", "") or ""))).strip() or "other"
        budget = int(family_budgets.get(family, max_files) or 0) if family_budgets else max_files
        family_used = int(family_counts.get(family, 0) or 0)
        within_rank = len(selected_files) < max_files
        within_family_budget = family_used < budget if family_budgets else family_used < budget
        if path_value and within_rank and within_family_budget:
            item["selected_for_processing"] = True
            item["exclusion_reason"] = ""
            item["selection_reason"] = _compose_selection_reason(
                family,
                str(selection_notes.get(family, "") or "").strip(),
                list(item.get("priority_boosts", []) or []),
            )
            item["skip_reason_detail"] = ""
            selected_files.append(path_value)
            selected_set.add(path_value)
            family_counts[family] = family_used + 1
        else:
            item["selected_for_processing"] = False
            item["selection_reason"] = ""
            if not within_rank:
                item["exclusion_reason"] = "deprioritized_by_ranking"
            else:
                item["exclusion_reason"] = "family_budget_exhausted"
            item["skip_reason_detail"] = _compose_skip_reason(
                str(item.get("exclusion_reason", "") or "").strip(),
                str(skip_notes.get(family, "") or "").strip(),
                list(item.get("priority_penalties", []) or []),
            )
    if len(selected_files) < max_files:
        for item in ranked_files:
            path_value = str(item.get("path", "")).strip()
            if not path_value or path_value in selected_set or len(selected_files) >= max_files:
                continue
            item["selected_for_processing"] = True
            item["exclusion_reason"] = ""
            item["selection_reason"] = _compose_selection_reason(
                str(item.get("source_family", "") or "other"),
                str(selection_notes.get(str(item.get("source_family", "") or "other"), "") or "").strip() or "Selected as overflow after primary family budgets were filled.",
                list(item.get("priority_boosts", []) or []),
            )
            item["skip_reason_detail"] = ""
            selected_files.append(path_value)
            selected_set.add(path_value)
    truncated = len(ranked_files) > max_files

    excluded_reason_counts: dict[str, int] = {}
    selected_type_counts: dict[str, int] = {}
    selected_family_counts: dict[str, int] = {}
    for item in files:
        reason = str(item.get("exclusion_reason", "") or "").strip()
        if reason:
            excluded_reason_counts[reason] = int(excluded_reason_counts.get(reason, 0) or 0) + 1
        if bool(item.get("selected_for_processing")):
            ext = str(item.get("extension", "") or "unknown").strip() or "unknown"
            selected_type_counts[ext] = int(selected_type_counts.get(ext, 0) or 0) + 1
            family = str(item.get("source_family", "") or "other").strip() or "other"
            selected_family_counts[family] = int(selected_family_counts.get(family, 0) or 0) + 1

    return {
        "roots": roots,
        "recursive": recursive,
        "include_hidden": include_hidden,
        "max_files": max_files,
        "objective": str(objective or "").strip(),
        "allowed_extensions": sorted(allowed_extensions),
        "selected_files": selected_files,
        "entries": entries,
        "folders": folders,
        "files": files,
        "entry_count": len(entries),
        "folder_count": len(folders),
        "file_count": len(files),
        "selected_file_count": len(selected_files),
        "excluded_file_count": len([item for item in files if not item.get("selected_for_processing")]),
        "excluded_reason_counts": excluded_reason_counts,
        "selected_type_counts": selected_type_counts,
        "selected_family_counts": selected_family_counts,
        "source_strategy": dict(strategy) if strategy else {},
        "truncated": truncated,
    }


def merge_documents(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_path = {}
    for item in existing or []:
        if isinstance(item, dict):
            by_path[str(item.get("path", ""))] = item
    for item in incoming or []:
        if isinstance(item, dict):
            by_path[str(item.get("path", ""))] = item
    return [item for key, item in sorted(by_path.items()) if key]


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return slug[:64] or "document"


def textual_sources_for_memory(state: dict[str, Any]) -> list[dict]:
    records = []
    for page in state.get("web_crawl_pages", []) or []:
        if page.get("text"):
            for index, chunk in enumerate(chunk_text(page["text"])):
                records.append(
                    {
                        "source": page.get("url", "web"),
                        "text": chunk,
                        "payload": {"source_type": "web_page", "chunk_index": index},
                    }
                )
    for document in state.get("documents", []) or []:
        if document.get("text"):
            for index, chunk in enumerate(chunk_text(document["text"])):
                records.append(
                    {
                        "source": document.get("path", "document"),
                        "text": chunk,
                        "payload": {"source_type": "document", "chunk_index": index},
                    }
                )
    for item in state.get("ocr_results", []) or []:
        if item.get("text"):
            records.append(
                {
                    "source": item.get("path", "ocr"),
                    "text": item["text"],
                    "payload": {"source_type": "ocr"},
                }
            )
    for item in state.get("local_drive_document_summaries", []) or []:
        summary_text = (item or {}).get("summary", "")
        if summary_text:
            records.append(
                {
                    "source": f"{item.get('path', 'document')}#summary",
                    "text": summary_text,
                    "payload": {"source_type": "document_summary", "document_type": item.get("type", "unknown")},
                }
            )
    return records


def maybe_upsert_memory(state: dict[str, Any], records: list[dict]):
    try:
        result = upsert_memory_records(records)
        state["memory_index_result"] = result
        return result
    except Exception as exc:
        state["memory_index_error"] = str(exc)
        return {"indexed": 0, "collection": "unavailable", "error": str(exc)}


def maybe_search_memory(state: dict[str, Any], query: str, top_k: int = 5) -> list[dict]:
    try:
        return search_memory(query, top_k=top_k)
    except Exception as exc:
        state["memory_search_error"] = str(exc)
        return []
