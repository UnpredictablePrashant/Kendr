import json
import os
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from kendr.rag_manager import build_research_grounding
from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.coding_tasks import _extract_output_text
from tasks.research_infra import fetch_url_content, llm_text, parse_documents
from tasks.research_output import render_phase0_report, split_sources_section
from tasks.utils import OUTPUT_DIR, log_task_update, write_text_file


DEFAULT_DEEP_RESEARCH_MODEL = os.getenv("OPENAI_DEEP_RESEARCH_MODEL", "o4-mini-deep-research")

AGENT_METADATA = {
    "deep_research_agent": {
        "description": "Runs OpenAI Deep Research for web-grounded, source-aware, in-depth research tasks.",
        "skills": ["deep", "research", "web", "citations", "analysis"],
        "input_keys": [
            "research_query",
            "research_model",
            "research_instructions",
            "research_max_tool_calls",
            "research_max_output_tokens",
            "research_web_search_enabled",
            "deep_research_source_urls",
            "local_drive_paths",
            "research_kb_enabled",
            "research_kb_id",
            "research_kb_top_k",
        ],
        "output_keys": [
            "research_result",
            "research_status",
            "research_response_id",
            "research_raw",
            "research_kb_used",
            "research_kb_name",
            "research_kb_hit_count",
            "research_kb_citations",
            "research_kb_warning",
            "research_source_summary",
            "deep_research_result_card",
        ],
        "requirements": ["openai"],
        "display_name": "Deep Research Agent",
        "category": "research",
        "intent_patterns": [
            "research this topic", "do deep research", "investigate in depth",
            "find citations", "source-backed analysis", "web research with sources",
        ],
        "active_when": ["env:OPENAI_API_KEY"],
        "config_hint": "Add your OpenAI API key in Setup → Providers.",
    }
}


def _serialize_response(response) -> dict:
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if isinstance(response, dict):
        return response
    return {"response": str(response)}


def _normalize_url_list(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        raw_items = raw_value.split(",")
    elif isinstance(raw_value, list):
        raw_items = raw_value
    else:
        raw_items = []
    urls: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        value = str(item or "").strip()
        if not value or not value.lower().startswith(("http://", "https://")):
            continue
        if value in seen:
            continue
        seen.add(value)
        urls.append(value)
    return urls


def _research_source_summary_lines(
    state: dict,
    *,
    local_meta: dict,
    kb_grounding: dict[str, Any],
) -> list[str]:
    lines: list[str] = []

    kb_name = str((kb_grounding or {}).get("kb_name", "") or "").strip()
    kb_hits = int((kb_grounding or {}).get("hit_count", 0) or 0)
    kb_citations = list((kb_grounding or {}).get("citations", []) or [])
    if kb_name or kb_hits or kb_citations:
        label = kb_name or "active knowledge base"
        hit_label = "hit" if kb_hits == 1 else "hits"
        lines.append(f"- Knowledge base: {label} ({kb_hits} {hit_label})")
        for citation in kb_citations[:5]:
            source_id = str(
                citation.get("source_id")
                or citation.get("uri")
                or citation.get("path")
                or citation.get("title")
                or ""
            ).strip()
            if source_id:
                lines.append(f"- KB source: {source_id}")

    local_file_count = int((local_meta or {}).get("local_file_count", 0) or 0)
    if local_file_count > 0:
        label = "file" if local_file_count == 1 else "files"
        lines.append(f"- Local {label} reviewed: {local_file_count}")

    provided_urls = _normalize_url_list(state.get("deep_research_source_urls", []))[:10]
    if provided_urls:
        for url in provided_urls:
            lines.append(f"- Provided URL: {url}")
    else:
        provided_url_count = int((local_meta or {}).get("provided_url_count", 0) or 0)
        if provided_url_count > 0:
            label = "URL" if provided_url_count == 1 else "URLs"
            lines.append(f"- Provided {label} reviewed: {provided_url_count}")

    return lines


def _research_coverage_lines(
    *,
    web_search_enabled: bool,
    model: str,
    local_meta: dict,
    kb_enabled: bool,
    kb_grounding: dict[str, Any],
    kb_warning: str,
) -> list[str]:
    lines = [
        f"Mode: {'web-backed' if web_search_enabled else 'local-only'}",
        f"Web search: {'enabled' if web_search_enabled else 'disabled'}",
        f"Model: {model if web_search_enabled else 'local-only-synthesis'}",
        f"Local files reviewed: {int((local_meta or {}).get('local_file_count', 0) or 0)}",
        f"Provided URLs reviewed: {int((local_meta or {}).get('provided_url_count', 0) or 0)}",
    ]

    kb_name = str((kb_grounding or {}).get("kb_name", "") or "").strip()
    kb_hits = int((kb_grounding or {}).get("hit_count", 0) or 0)
    if kb_enabled or kb_name or kb_hits:
        lines.append(f"Knowledge base: {kb_name or 'configured'}")
        lines.append(f"Knowledge base hits: {kb_hits}")
    else:
        lines.append("Knowledge base: disabled")

    if kb_warning:
        lines.append(f"Knowledge base note: {kb_warning}")
    return lines


def _research_next_steps(
    *,
    web_search_enabled: bool,
    local_meta: dict,
    kb_enabled: bool,
    kb_grounding: dict[str, Any],
) -> list[str]:
    steps: list[str] = []
    if int((local_meta or {}).get("local_file_count", 0) or 0) > 0:
        steps.append("Review the highest-signal local files for exact numbers, dates, and quotations before sharing this brief.")
    if web_search_enabled or int((local_meta or {}).get("provided_url_count", 0) or 0) > 0:
        steps.append("Cross-check the highest-impact claims against a second independent source before treating them as final.")
    if int((kb_grounding or {}).get("hit_count", 0) or 0) > 0:
        steps.append("Inspect the cited knowledge-base entries to confirm they still match the current evidence set.")
    elif kb_enabled:
        steps.append("Rebuild or retune the knowledge-base index if you expected internal grounding for this query.")
    if not steps:
        steps.append("Gather at least one primary source before relying on this brief for external decisions.")
    return steps[:3]


def _build_research_result_card(
    *,
    query: str,
    web_search_enabled: bool,
    local_meta: dict,
    kb_grounding: dict[str, Any],
    kb_warning: str,
    source_summary: list[str],
) -> dict[str, Any]:
    return {
        "kind": "brief",
        "title": "Deep Research Brief",
        "query": query,
        "mode": "web" if web_search_enabled else "local_only",
        "web_search_enabled": web_search_enabled,
        "local_sources": int((local_meta or {}).get("local_file_count", 0) or 0),
        "provided_urls": int((local_meta or {}).get("provided_url_count", 0) or 0),
        "research_kb_used": bool((kb_grounding or {}).get("prompt_context")),
        "research_kb_name": str((kb_grounding or {}).get("kb_name", "") or ""),
        "research_kb_hit_count": int((kb_grounding or {}).get("hit_count", 0) or 0),
        "research_kb_citations": list((kb_grounding or {}).get("citations", []) or []),
        "research_kb_warning": kb_warning,
        "source_summary": list(source_summary or []),
    }


def _build_local_source_context(state: dict, query: str, *, include_urls: bool) -> tuple[str, dict]:
    blocks: list[str] = []
    meta = {"local_file_count": 0, "provided_url_count": 0}

    local_drive_paths = [str(item).strip() for item in list(state.get("local_drive_paths") or []) if str(item).strip()]
    local_docs = state.get("local_drive_documents") if isinstance(state.get("local_drive_documents"), list) else []
    if not local_docs and local_drive_paths:
        local_docs = parse_documents(
            local_drive_paths,
            continue_on_error=True,
            ocr_images=bool(state.get("local_drive_enable_image_ocr", True)),
            ocr_instruction=state.get("local_drive_ocr_instruction"),
        )
    for index, doc in enumerate(local_docs[:12], start=1):
        path_value = str(doc.get("path", "")).strip()
        text_value = str(doc.get("text", "")).strip()[:2500]
        meta["local_file_count"] += 1
        blocks.append(
            "\n".join(
                [
                    f"[Local File {index}] {Path(path_value).name or path_value or 'document'}",
                    f"Path: {path_value or 'n/a'}",
                    text_value or "No readable text extracted.",
                ]
            )
        )

    if include_urls:
        provided_urls = _normalize_url_list(state.get("deep_research_source_urls", []))[:10]
        for index, url in enumerate(provided_urls, start=1):
            page = dict(fetch_url_content(url, timeout=20) or {})
            if page.get("error"):
                page_text = f"URL extraction failed: {page.get('error')}"
            else:
                page_text = str(page.get("text", "")).strip()[:2500]
            meta["provided_url_count"] += 1
            blocks.append(
                "\n".join(
                    [
                        f"[Provided URL {index}] {url}",
                        page_text or "No readable text extracted.",
                    ]
                )
            )

    if not blocks:
        return "", meta

    prompt = f"""
You are preparing source context for a deep research run.

Research objective:
{query}

Available local source material:
{chr(10).join(blocks)[:22000]}

Produce a concise source memo with:
- strongest facts and evidence
- important numbers, dates, entities
- contradictions or gaps
- which sources appear most relevant
"""
    return llm_text(prompt).strip(), meta


def deep_research_agent(state):
    active_task, task_content, _ = begin_agent_session(state, "deep_research_agent")
    state["deep_research_calls"] = state.get("deep_research_calls", 0) + 1
    call_number = state["deep_research_calls"]

    query = state.get("research_query") or task_content or state.get("current_objective") or state.get("user_query", "").strip()
    if not query:
        raise ValueError("deep_research_agent requires 'research_query' or 'user_query' in state.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for deep_research_agent.")

    model = state.get("research_model", DEFAULT_DEEP_RESEARCH_MODEL)
    max_tool_calls = int(state.get("research_max_tool_calls", 8))
    max_output_tokens = state.get("research_max_output_tokens")
    instructions = state.get(
        "research_instructions",
        "Conduct a careful web-based deep research pass. Synthesize the results clearly, cite concrete sources when available, and call out uncertainty.",
    )
    web_search_enabled = bool(state.get("research_web_search_enabled", True))
    background = state.get("research_background", True)
    poll_interval_seconds = int(state.get("research_poll_interval_seconds", 5))
    max_wait_seconds = int(state.get("research_max_wait_seconds", 600))
    kb_enabled = bool(state.get("research_kb_enabled", False))
    kb_ref = str(state.get("research_kb_id", "") or "").strip()
    kb_top_k = max(1, int(state.get("research_kb_top_k", 8) or 8))

    local_context, local_meta = _build_local_source_context(state, query, include_urls=True)
    has_non_kb_evidence = bool(
        web_search_enabled
        or int(local_meta.get("local_file_count", 0) or 0) > 0
        or int(local_meta.get("provided_url_count", 0) or 0) > 0
    )
    kb_warning = ""
    kb_grounding: dict[str, Any] = {}
    if kb_enabled:
        try:
            kb_grounding = build_research_grounding(
                query,
                kb_ref=kb_ref,
                top_k=kb_top_k,
                use_active_if_empty=True,
                require_indexed=True,
            )
        except Exception as exc:
            kb_warning = str(exc)
            if has_non_kb_evidence:
                log_task_update(
                    "Deep Research",
                    f"Knowledge base grounding unavailable; continuing with other sources. {kb_warning}",
                )
            else:
                raise ValueError(
                    f"Knowledge base grounding failed and no other evidence sources are available. {kb_warning}"
                ) from exc
        else:
            if int(kb_grounding.get("hit_count", 0) or 0) <= 0:
                kb_warning = (
                    f"Knowledge base '{kb_grounding.get('kb_name', 'unknown')}' returned no relevant results for this query."
                )
            if kb_grounding.get("prompt_context"):
                instructions = (
                    f"{instructions}\n\n"
                    "Prioritize the supplied knowledge-base grounding and explicitly reconcile it with any other findings.\n\n"
                    f"{kb_grounding['prompt_context']}"
                )
            elif not has_non_kb_evidence and not web_search_enabled:
                raise ValueError(
                    f"{kb_warning} No other evidence sources are available for this local-only run."
                )
    if local_context:
        instructions = (
            f"{instructions}\n\n"
            "Prioritize the supplied local source context and explicitly reconcile it with any additional findings.\n\n"
            f"Local source context:\n{local_context}"
        )
    combined_source_context = "\n\n".join(
        part
        for part in (kb_grounding.get("prompt_context", ""), local_context)
        if str(part).strip()
    ).strip()
    source_summary = _research_source_summary_lines(state, local_meta=local_meta, kb_grounding=kb_grounding)
    coverage_summary = _research_coverage_lines(
        web_search_enabled=web_search_enabled,
        model=str(model),
        local_meta=local_meta,
        kb_enabled=kb_enabled,
        kb_grounding=kb_grounding,
        kb_warning=kb_warning,
    )
    recommended_next_steps = _research_next_steps(
        web_search_enabled=web_search_enabled,
        local_meta=local_meta,
        kb_enabled=kb_enabled,
        kb_grounding=kb_grounding,
    )
    result_card = _build_research_result_card(
        query=query,
        web_search_enabled=web_search_enabled,
        local_meta=local_meta,
        kb_grounding=kb_grounding,
        kb_warning=kb_warning,
        source_summary=source_summary,
    )

    if not web_search_enabled:
        local_only_prompt = f"""
You are conducting a deep research pass without internet or web search.

Research query:
{query}

Available source context:
{combined_source_context or "No local file context was provided."}

Write a source-aware research memo that:
- uses only the provided source context
- does not invent external citations
- calls out gaps or uncertainty clearly
- ends with a concise recommended next-steps section
"""
        raw_output_text = llm_text(local_only_prompt).strip()
        findings_text, cited_sources = split_sources_section(raw_output_text)
        output_text = render_phase0_report(
            title="Deep Research Brief",
            objective=query,
            findings=findings_text or raw_output_text,
            coverage_lines=coverage_summary,
            next_steps=recommended_next_steps,
            sources_lines=[*source_summary, *cited_sources],
        )
        payload = {
            "mode": "local_only",
            "query": query,
            "local_context": combined_source_context,
            "local_source_count": local_meta.get("local_file_count", 0),
            "provided_url_count": local_meta.get("provided_url_count", 0),
            "research_kb": kb_grounding,
            "research_kb_used": bool(kb_grounding.get("prompt_context")),
            "research_kb_warning": kb_warning,
            "source_summary": [*source_summary, *cited_sources],
            "coverage_summary": coverage_summary,
            "recommended_next_steps": recommended_next_steps,
            "raw_output_text": raw_output_text,
            "output_text": output_text,
        }
        raw_filename = f"deep_research_raw_{call_number}.json"
        output_filename = f"deep_research_output_{call_number}.txt"
        write_text_file(raw_filename, json.dumps(payload, indent=2, ensure_ascii=False))
        write_text_file(output_filename, output_text)
        state["research_response_id"] = f"local_only_{call_number}"
        state["research_status"] = "completed"
        state["research_result"] = output_text
        state["research_model"] = "local-only-synthesis"
        state["research_raw"] = payload
        state["research_kb_used"] = bool(payload.get("research_kb_used"))
        state["research_kb_name"] = str((kb_grounding or {}).get("kb_name", "") or "")
        state["research_kb_hit_count"] = int((kb_grounding or {}).get("hit_count", 0) or 0)
        state["research_kb_citations"] = list((kb_grounding or {}).get("citations", []) or [])
        state["research_kb_warning"] = kb_warning
        state["research_source_summary"] = payload["source_summary"]
        state["deep_research_result_card"] = {
            **result_card,
            "source_summary": list(payload["source_summary"]),
        }
        state["draft_response"] = output_text
        log_task_update(
            "Deep Research",
            (
                f"Completed local-only deep research run #{call_number} using "
                f"{local_meta.get('local_file_count', 0)} local file(s), "
                f"{local_meta.get('provided_url_count', 0)} provided URL(s), and "
                f"{int((kb_grounding or {}).get('hit_count', 0) or 0)} KB hit(s)."
            ),
            output_text,
        )
        state = publish_agent_output(
            state,
            "deep_research_agent",
            output_text,
            f"deep_research_result_{call_number}",
            recipients=["orchestrator_agent", "worker_agent"],
        )
        return state

    client = OpenAI(api_key=api_key)

    log_task_update(
        "Deep Research",
        f"Research pass #{call_number} started with model '{model}'.",
        query,
    )

    create_kwargs = {
        "model": model,
        "input": query,
        "instructions": instructions,
        "background": background,
        "max_tool_calls": max_tool_calls,
        "reasoning": {"summary": "auto"},
        "tools": [{"type": "web_search_preview"}],
    }
    if max_output_tokens is not None:
        create_kwargs["max_output_tokens"] = int(max_output_tokens)

    response = client.responses.create(**create_kwargs)
    response_id = response.id
    status = getattr(response, "status", "unknown")

    log_task_update(
        "Deep Research",
        f"Research job created with response id '{response_id}' and initial status '{status}'.",
    )

    elapsed_seconds = 0
    while background and status not in {"completed", "failed", "cancelled", "incomplete"}:
        if elapsed_seconds >= max_wait_seconds:
            raise TimeoutError(
                f"Deep research job '{response_id}' did not finish within {max_wait_seconds} seconds."
            )

        time.sleep(poll_interval_seconds)
        elapsed_seconds += poll_interval_seconds
        response = client.responses.retrieve(response_id)
        new_status = getattr(response, "status", "unknown")

        if new_status != status:
            status = new_status
            log_task_update(
                "Deep Research",
                f"Research job '{response_id}' status changed to '{status}' after {elapsed_seconds} seconds.",
            )
        else:
            log_task_update(
                "Deep Research",
                f"Research job '{response_id}' still '{status}' after {elapsed_seconds} seconds.",
            )

    payload = _serialize_response(response)
    payload["research_kb"] = kb_grounding
    payload["research_kb_used"] = bool(kb_grounding.get("prompt_context"))
    payload["research_kb_warning"] = kb_warning
    raw_output_text = getattr(response, "output_text", None) or _extract_output_text(payload)
    findings_text, cited_sources = split_sources_section(raw_output_text)
    payload["source_summary"] = [*source_summary, *cited_sources]
    payload["coverage_summary"] = coverage_summary
    payload["recommended_next_steps"] = recommended_next_steps
    payload["raw_output_text"] = raw_output_text
    output_text = render_phase0_report(
        title="Deep Research Brief",
        objective=query,
        findings=findings_text or raw_output_text,
        coverage_lines=coverage_summary,
        next_steps=recommended_next_steps,
        sources_lines=payload["source_summary"],
    )
    payload["output_text"] = output_text

    raw_filename = f"deep_research_raw_{call_number}.json"
    output_filename = f"deep_research_output_{call_number}.txt"

    write_text_file(raw_filename, json.dumps(payload, indent=2, ensure_ascii=False))
    write_text_file(output_filename, output_text)

    state["research_response_id"] = response_id
    state["research_status"] = getattr(response, "status", status)
    state["research_result"] = output_text
    state["research_model"] = model
    state["research_raw"] = payload
    state["research_kb_used"] = bool(payload.get("research_kb_used"))
    state["research_kb_name"] = str((kb_grounding or {}).get("kb_name", "") or "")
    state["research_kb_hit_count"] = int((kb_grounding or {}).get("hit_count", 0) or 0)
    state["research_kb_citations"] = list((kb_grounding or {}).get("citations", []) or [])
    state["research_kb_warning"] = kb_warning
    state["research_source_summary"] = payload["source_summary"]
    state["deep_research_result_card"] = {
        **result_card,
        "source_summary": list(payload["source_summary"]),
    }
    state["draft_response"] = output_text

    log_task_update(
        "Deep Research",
        (
            f"Deep research finished with status '{state['research_status']}'. "
            f"Saved artifacts to {OUTPUT_DIR}/{output_filename}. "
            f"KB hits: {int((kb_grounding or {}).get('hit_count', 0) or 0)}."
        ),
        output_text,
    )
    state = publish_agent_output(
        state,
        "deep_research_agent",
        output_text,
        f"deep_research_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent"],
    )
    return state
