from __future__ import annotations

import re
from typing import Any, Mapping


_MARKERS: dict[str, set[str]] = {
    "market": {"market", "competitor", "industry", "pricing", "growth", "customer", "buyer", "seller", "diligence"},
    "technical": {"technical", "architecture", "system", "platform", "aws", "cloud", "deployment", "integration", "failure", "simulation"},
    "academic": {"paper", "journal", "study", "citation", "peer", "literature", "academic", "research"},
    "compliance": {"policy", "regulation", "regulatory", "privacy", "compliance", "legal", "gdpr", "soc2", "iso", "audit"},
    "codebase": {"code", "repository", "repo", "source", "implementation", "module", "service", "api", "stack", "class", "function"},
    "tables": {"table", "spreadsheet", "excel", "xlsx", "xls", "csv", "financial", "forecast", "revenue", "budget", "metrics"},
    "images": {"image", "diagram", "chart", "slide", "deck", "ppt", "pptx", "screenshot"},
    "brief": {"brief", "summary", "short", "one-pager"},
    "report": {"report", "research", "whitepaper", "guide", "handbook"},
    "memo": {"memo", "note"},
    "comparison": {"compare", "comparison", "versus", "vs"},
    "diligence_pack": {"diligence", "investment", "due", "acquisition"},
    "high_stakes": {"medical", "legal", "compliance", "regulation", "financial", "security", "privacy"},
}

_FAMILY_PREFERRED_EXTENSIONS = {
    "document": [".pdf", ".docx", ".doc", ".md", ".txt", ".html", ".htm"],
    "presentation": [".pptx", ".ppt", ".pptm"],
    "spreadsheet": [".xlsx", ".xls", ".xlsm", ".csv"],
    "code": [".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".sql"],
    "config": [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".xml"],
    "image": [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"],
}


def _tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_+-]{2,}", str(value or "").lower()) if token}


def _score_markers(tokens: set[str], marker_key: str) -> int:
    markers = _MARKERS.get(marker_key, set())
    return len(tokens & markers)


def _pick_research_kind(tokens: set[str]) -> tuple[str, list[str]]:
    scores = {
        "market": _score_markers(tokens, "market"),
        "technical": _score_markers(tokens, "technical"),
        "academic": _score_markers(tokens, "academic"),
        "compliance": _score_markers(tokens, "compliance"),
        "codebase": _score_markers(tokens, "codebase"),
    }
    non_zero = [kind for kind, score in scores.items() if score > 0]
    if len(non_zero) >= 2:
        return "mixed", non_zero
    if non_zero:
        return non_zero[0], non_zero
    return "market", []


def _pick_deliverable(tokens: set[str]) -> str:
    for name in ("diligence_pack", "comparison", "memo", "brief", "report"):
        if _score_markers(tokens, name) > 0:
            return name.replace("_", " ")
    return "report"


def _source_needs(tokens: set[str], research_kind: str) -> list[str]:
    needs: list[str] = []
    if _score_markers(tokens, "tables") > 0:
        needs.append("tables")
    if _score_markers(tokens, "images") > 0:
        needs.append("images")
    if research_kind in {"codebase", "technical", "mixed"} or _score_markers(tokens, "codebase") > 0:
        needs.append("code")
    if research_kind != "codebase":
        needs.append("local docs")
    if research_kind in {"market", "technical", "academic", "compliance", "mixed"}:
        needs.append("web")
    seen: set[str] = set()
    normalized: list[str] = []
    for item in needs:
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized or ["local docs"]


def discover_research_intent(objective: str, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    tokens = _tokenize(objective)
    research_kind, matched_kinds = _pick_research_kind(tokens)
    deliverable = _pick_deliverable(tokens)
    source_needs = _source_needs(tokens, research_kind)
    risk_level = "high-stakes" if _score_markers(tokens, "high_stakes") > 0 else "normal"
    docs_first = research_kind != "codebase" and "codebase" not in matched_kinds
    allow_code = "code" in source_needs
    intent = {
        "research_kind": research_kind,
        "matched_kinds": matched_kinds,
        "target_deliverable": deliverable,
        "source_needs": source_needs,
        "risk_level": risk_level,
        "docs_first": docs_first,
        "code_relevant": allow_code,
        "table_relevant": "tables" in source_needs,
        "image_relevant": "images" in source_needs,
        "banned_actions": ["build_code", "mutate_repo", "request_blueprint"],
        "summary": (
            f"{research_kind} research targeting a {deliverable}; "
            f"source mix={', '.join(source_needs)}; risk={risk_level}."
        ),
    }
    if isinstance(state, Mapping):
        intent["workflow_type"] = str(state.get("workflow_type", "") or "").strip()
    return intent


def _weighted_budget(max_files: int, weights: Mapping[str, int]) -> dict[str, int]:
    total_weight = max(1, sum(max(0, int(value)) for value in weights.values()))
    allocated: dict[str, int] = {}
    remaining = max_files
    ordered = list(weights.keys())
    for index, family in enumerate(ordered):
        weight = max(0, int(weights.get(family, 0) or 0))
        if weight <= 0:
            allocated[family] = 0
            continue
        if index == len(ordered) - 1:
            allocated[family] = remaining
            break
        amount = max(0, round((max_files * weight) / total_weight))
        amount = min(amount, remaining)
        allocated[family] = amount
        remaining -= amount
    for family in ordered:
        allocated.setdefault(family, 0)
    return allocated


def build_source_strategy(
    intent: Mapping[str, Any],
    *,
    max_files: int,
    allow_web_search: bool,
    local_paths_present: bool,
) -> dict[str, Any]:
    research_kind = str(intent.get("research_kind", "market") or "market").strip().lower()
    docs_first = bool(intent.get("docs_first", True))
    table_relevant = bool(intent.get("table_relevant", False))
    image_relevant = bool(intent.get("image_relevant", False))
    code_relevant = bool(intent.get("code_relevant", False))

    if research_kind == "codebase":
        weights = {"code": 40, "config": 18, "document": 16, "spreadsheet": 8, "presentation": 6, "image": 4, "other": 8}
    elif docs_first:
        weights = {"document": 38, "presentation": 18, "spreadsheet": 14, "code": 8, "config": 8, "image": 6, "other": 8}
    else:
        weights = {"document": 24, "presentation": 14, "spreadsheet": 12, "code": 18, "config": 12, "image": 6, "other": 14}

    if table_relevant:
        weights["spreadsheet"] += 8
    if image_relevant:
        weights["presentation"] += 6
        weights["image"] += 6
    if code_relevant and research_kind != "codebase":
        weights["code"] += 8
        weights["config"] += 5

    family_budgets = _weighted_budget(max_files=max_files, weights=weights)
    preferred_extensions: list[str] = []
    for family in ("document", "presentation", "spreadsheet", "code", "config", "image"):
        preferred_extensions.extend(_FAMILY_PREFERRED_EXTENSIONS.get(family, []))

    selection_notes = {
        "document": "Selected because documents usually contain the highest-signal narrative evidence for this research objective.",
        "presentation": "Selected because slide decks often surface executive summaries, charts, and conclusion slides quickly.",
        "spreadsheet": "Selected because tabular files often contain concrete numbers, forecasts, and model inputs.",
        "code": "Selected because this objective likely depends on implementation details, APIs, or system behavior.",
        "config": "Selected because configuration files often explain environment, dependencies, and runtime architecture.",
        "image": "Selected because images may contain screenshots, charts, or scanned evidence worth OCR.",
        "other": "Selected as overflow after higher-priority evidence families were exhausted.",
    }
    skip_notes = {
        "document": "Skipped because higher-priority document files exhausted the document budget first.",
        "presentation": "Skipped because higher-priority slide decks exhausted the presentation budget first.",
        "spreadsheet": "Skipped because higher-priority tables and spreadsheet files exhausted the spreadsheet budget first.",
        "code": "Skipped because code evidence was lower priority than core document evidence for this run.",
        "config": "Skipped because configuration evidence was lower priority than core document evidence for this run.",
        "image": "Skipped because image/OCR evidence was lower priority than directly readable files for this run.",
        "other": "Skipped because the run budget was reserved for more relevant evidence families.",
    }

    selection_rationale = []
    if docs_first:
        selection_rationale.append("Docs-first weighting applied.")
    if code_relevant:
        selection_rationale.append("Code/config admitted because technical understanding may matter.")
    if table_relevant:
        selection_rationale.append("Spreadsheet/table budget increased because numeric evidence matters.")
    if image_relevant:
        selection_rationale.append("Presentation/image budget increased because slides or visuals may matter.")

    return {
        "mode": "docs_first" if docs_first else "mixed",
        "family_budgets": family_budgets,
        "preferred_extensions": preferred_extensions,
        "allow_code_files": code_relevant,
        "allow_web_search": allow_web_search,
        "web_search_needed": allow_web_search and research_kind != "codebase",
        "local_paths_present": bool(local_paths_present),
        "selection_notes": selection_notes,
        "skip_notes": skip_notes,
        "selection_rationale": selection_rationale,
        "summary": (
            f"Prioritize {('documents, presentations, and spreadsheets' if docs_first else 'a mixed evidence set')}; "
            f"web_search={'yes' if allow_web_search and research_kind != 'codebase' else 'no'}."
        ),
    }
