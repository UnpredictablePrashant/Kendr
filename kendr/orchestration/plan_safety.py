from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

_READ_ONLY_AGENT_PREFIXES = (
    "local_drive_",
    "people_research_",
    "company_research_",
    "deep_research_",
    "search_",
    "research_",
    "report_",
    "intelligence_",
)

_READ_ONLY_AGENT_NAMES = {
    "local_drive_agent",
    "people_research_agent",
    "company_research_agent",
    "deep_research_agent",
    "report_agent",
    "search_agent",
    "worker_agent",
}

_WRITE_AGENT_MARKERS = (
    "os_",
    "github_",
    "coding_",
    "factory_",
    "builder_",
    "deploy",
    "scaffold",
    "scheduler",
    "desktop_automation",
    "notification_dispatch",
)

_READ_ONLY_TASK_RE = re.compile(
    r"\b("
    r"analy[sz]e|assess|audit|catalog|check|collect|compare|discover|enumerate|extract|find|gather|"
    r"inspect|investigate|list|look\s+up|read|research|review|scan|search|study|summari[sz]e|survey|trace|verify"
    r")\b",
    re.IGNORECASE,
)

_WRITE_TASK_RE = re.compile(
    r"\b("
    r"apply|branch|build|change|clone|commit|configure|create|delete|deploy|draft|edit|execute|fix|"
    r"generate|install|merge|modify|move|open|patch|post|publish|push|refactor|remove|rename|replace|"
    r"run|schedule|send|start|stop|submit|update|write"
    r")\b",
    re.IGNORECASE,
)

_EXTERNAL_ACTION_RE = re.compile(
    r"\b(email|message|notify|post|purchase|schedule|send|share|sms|submit|transfer|upload)\b",
    re.IGNORECASE,
)

_PATH_RE = re.compile(r"`([^`]+)`|([A-Za-z]:\\\\[^\\s]+)|(/[^\\s]+)")


def _normalize_agent_lookup(agent_lookup: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    if not isinstance(agent_lookup, Mapping):
        return normalized
    for name, payload in agent_lookup.items():
        if not str(name).strip():
            continue
        if isinstance(payload, Mapping):
            normalized[str(name).strip()] = dict(payload)
        else:
            normalized[str(name).strip()] = {}
    return normalized


def _agent_metadata(agent_name: str, agent_lookup: Mapping[str, Any] | None = None) -> dict[str, Any]:
    normalized = _normalize_agent_lookup(agent_lookup)
    return normalized.get(str(agent_name).strip(), {})


def infer_step_side_effect_level(
    step: Mapping[str, Any],
    *,
    agent_lookup: Mapping[str, Any] | None = None,
) -> str:
    existing = str(step.get("side_effect_level", "") or "").strip().lower()
    if existing in {"read_only", "isolated_write", "shared_write", "external_action"}:
        return existing

    agent_name = str(step.get("agent", "") or "").strip()
    metadata = _agent_metadata(agent_name, agent_lookup)
    declared_level = str(metadata.get("side_effect_level", "") or "").strip().lower()
    if declared_level in {"read_only", "isolated_write", "shared_write", "external_action"}:
        return declared_level
    if metadata.get("read_only") is True:
        return "read_only"

    lowered_agent = agent_name.lower()
    text = " ".join(
        [
            str(step.get("title", "") or ""),
            str(step.get("task", "") or ""),
            str(step.get("success_criteria", "") or ""),
        ]
    ).strip()

    if lowered_agent.startswith("mcp_") or lowered_agent.startswith("skill_"):
        return "unknown"

    if _EXTERNAL_ACTION_RE.search(text):
        return "external_action"
    if _WRITE_TASK_RE.search(text):
        if any(marker in text.lower() for marker in ("file", "code", "repo", "branch", "config", "command", "script", "test")):
            return "shared_write"
        return "isolated_write"

    if any(marker in lowered_agent for marker in _WRITE_AGENT_MARKERS):
        return "shared_write"

    if agent_name in _READ_ONLY_AGENT_NAMES or any(lowered_agent.startswith(prefix) for prefix in _READ_ONLY_AGENT_PREFIXES):
        return "read_only"

    if _READ_ONLY_TASK_RE.search(text) and not _WRITE_TASK_RE.search(text):
        return "read_only"
    return "unknown"


def infer_conflict_keys(
    step: Mapping[str, Any],
    *,
    agent_lookup: Mapping[str, Any] | None = None,
) -> list[str]:
    raw = step.get("conflict_keys", [])
    if isinstance(raw, list):
        normalized = [str(item).strip() for item in raw if str(item).strip()]
        if normalized:
            return normalized

    agent_name = str(step.get("agent", "") or "").strip() or "unknown-agent"
    side_effect_level = infer_step_side_effect_level(step, agent_lookup=agent_lookup)
    if side_effect_level == "read_only":
        return [f"agent:{agent_name}"]

    extracted_paths: list[str] = []
    text = " ".join(
        [
            str(step.get("title", "") or ""),
            str(step.get("task", "") or ""),
            str(step.get("success_criteria", "") or ""),
        ]
    )
    for match in _PATH_RE.finditer(text):
        path_value = next((group for group in match.groups() if group), "")
        if path_value:
            extracted_paths.append(path_value)
    if extracted_paths:
        return [f"path:{value}" for value in extracted_paths]
    return [f"agent:{agent_name}"]


def annotate_plan_steps(
    steps: list[dict[str, Any]],
    *,
    agent_lookup: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        updated = deepcopy(step)
        updated["side_effect_level"] = infer_step_side_effect_level(updated, agent_lookup=agent_lookup)
        updated["conflict_keys"] = infer_conflict_keys(updated, agent_lookup=agent_lookup)
        annotated.append(updated)
    return annotated


def plan_is_read_only(
    steps: list[dict[str, Any]],
    *,
    agent_lookup: Mapping[str, Any] | None = None,
) -> bool:
    annotated = annotate_plan_steps(steps, agent_lookup=agent_lookup)
    if not annotated:
        return False
    return all(str(step.get("side_effect_level", "")).strip().lower() == "read_only" for step in annotated)


def can_parallelize_step_batch(
    steps: list[dict[str, Any]],
    *,
    agent_lookup: Mapping[str, Any] | None = None,
) -> bool:
    annotated = annotate_plan_steps(steps, agent_lookup=agent_lookup)
    if len(annotated) < 2:
        return False
    seen_conflicts: set[str] = set()
    for step in annotated:
        if str(step.get("side_effect_level", "")).strip().lower() != "read_only":
            return False
        conflicts = step.get("conflict_keys", [])
        if not isinstance(conflicts, list):
            return False
        normalized = [str(item).strip() for item in conflicts if str(item).strip()]
        overlap = seen_conflicts.intersection(normalized)
        if overlap:
            return False
        seen_conflicts.update(normalized)
    return True
