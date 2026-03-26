from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tasks.research_infra import LOCAL_DRIVE_SUPPORTED_EXTENSIONS, chunk_text, search_memory, upsert_memory_records


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
) -> list[str]:
    discovered = []
    seen = set()
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
            if path.suffix.lower() not in allowed_extensions:
                continue
            discovered.append(str(path))
            seen.add(path)
            if len(discovered) >= max_files:
                return discovered
    return discovered


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
