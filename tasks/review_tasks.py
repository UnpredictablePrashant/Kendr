import json

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output, recent_messages_for_agent
from tasks.utils import OUTPUT_DIR, llm, log_task_update, model_for_agent, normalize_llm_text, write_text_file


def _strip_code_fences(text: str) -> str:
    stripped = normalize_llm_text(text).strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _estimate_safe_context_tokens(provider: str, model: str) -> int:
    """Return 75 % of the estimated context window (tokens) for prompt selection.

    Ollama's default num_ctx is often 2048-4096 regardless of the model's
    theoretical maximum, so cap conservatively at 8 192 for that provider.
    """
    from kendr.llm_router import get_context_window, PROVIDER_OLLAMA

    window = get_context_window(model)
    if provider == PROVIDER_OLLAMA:
        window = min(window, 8192)
    return int(window * 0.75)


def _build_detailed_prompt(
    current_objective, user_query, latest_agent, planned_step_id,
    planned_step_title, planned_step_success, revision_attempts,
    latest_output, recent_history, allowed_text,
) -> str:
    """Full-detail prompt for large-context models (GPT-4o, Claude, Gemini, etc.)."""
    output_trimmed = (latest_output or "")[:4000]
    history_trimmed = []
    for h in recent_history[-8:]:
        entry = dict(h)
        if "output_excerpt" in entry:
            entry["output_excerpt"] = str(entry["output_excerpt"] or "")[:500]
        history_trimmed.append(entry)

    return f"""You are a strict workflow reviewer in a multi-agent system.
Review if the latest agent output satisfies the current step's success criteria.

Current objective: {current_objective}
Original user query: {user_query}
Latest agent: {latest_agent}
Step id: {planned_step_id or 'n/a'} | Title: {planned_step_title or 'n/a'}
Success criteria: {planned_step_success or 'n/a'}
Prior revisions: {revision_attempts}

Latest output:
{output_trimmed}

Recent history (last 8 steps):
{json.dumps(history_trimmed, indent=2)}

Rules:
- Approve if the output materially satisfies the success criteria.
- Only revise if you can name a concrete, fixable deficiency.
- Do NOT revise just because the output is imperfect.
- If prior_revisions >= 2, approve unless critically broken.
- next_agent must be one of: {allowed_text}, finish

Return ONLY valid JSON, no extra text:
{{"decision":"approve","reason":"","is_output_correct":true,"revised_objective":"{current_objective}","step_reviews":[{{"agent":"{latest_agent}","status":"correct","notes":""}}],"next_agent":"finish","corrected_values":{{}}}}

Or if revising:
{{"decision":"revise","reason":"specific deficiency","is_output_correct":false,"revised_objective":"...","step_reviews":[{{"agent":"{latest_agent}","status":"needs_revision","notes":"..."}}],"next_agent":"worker_agent","corrected_values":{{}}}}
"""


def _build_compact_prompt(
    current_objective, user_query, latest_agent, planned_step_id,
    planned_step_title, planned_step_success, revision_attempts,
    latest_output, recent_history, allowed_text,
) -> str:
    """Minimal prompt for small-context models (llama3.2, mistral-7b, etc.)."""
    output_trimmed = (latest_output or "")[:1200]
    history_trimmed = []
    for h in recent_history[-3:]:
        entry = dict(h)
        if "output_excerpt" in entry:
            entry["output_excerpt"] = str(entry["output_excerpt"] or "")[:200]
        history_trimmed.append(entry)

    return f"""You are a strict workflow reviewer in a multi-agent system.
Review if the latest agent output satisfies the current step's success criteria.

Current objective: {current_objective}
Original user query: {user_query}
Latest agent: {latest_agent}
Step id: {planned_step_id or 'n/a'} | Title: {planned_step_title or 'n/a'}
Success criteria: {planned_step_success or 'n/a'}
Prior revisions: {revision_attempts}

Latest output (truncated):
{output_trimmed}

Recent history (last 3 steps):
{json.dumps(history_trimmed, indent=2)}

Rules:
- Approve if the output materially satisfies the success criteria.
- Only revise if you can name a concrete, fixable deficiency.
- Do NOT revise just because the output is imperfect.
- If prior_revisions >= 2, approve unless critically broken.
- next_agent must be one of: {allowed_text}, finish

Return ONLY valid JSON, no extra text:
{{"decision":"approve","reason":"","is_output_correct":true,"revised_objective":"{current_objective}","step_reviews":[{{"agent":"{latest_agent}","status":"correct","notes":""}}],"next_agent":"finish","corrected_values":{{}}}}

Or if revising:
{{"decision":"revise","reason":"specific deficiency","is_output_correct":false,"revised_objective":"...","step_reviews":[{{"agent":"{latest_agent}","status":"needs_revision","notes":"..."}}],"next_agent":"worker_agent","corrected_values":{{}}}}
"""


def _parse_review_output(raw_output: str) -> dict:
    cleaned = _strip_code_fences(raw_output)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("Reviewer output must be a JSON object.")
    return data


def reviewer_agent(state):
    active_task, task_content, _ = begin_agent_session(state, "reviewer_agent")
    state["reviewer_calls"] = state.get("reviewer_calls", 0) + 1
    a2a_context = recent_messages_for_agent(state, "reviewer_agent")
    current_objective = state.get("current_objective") or state["user_query"]
    latest_output = state.get("last_agent_output") or state.get("draft_response", "")
    latest_agent = state.get("last_agent", "unknown")
    planned_step_id = str(
        state.get("last_completed_plan_step_id")
        or state.get("current_plan_step_id")
        or ""
    ).strip()
    planned_step_title = str(
        state.get("last_completed_plan_step_title")
        or state.get("current_plan_step_title")
        or ""
    ).strip()
    planned_step_success = str(
        state.get("last_completed_plan_step_success_criteria")
        or state.get("current_plan_step_success_criteria")
        or ""
    ).strip()
    revision_counts = state.get("review_revision_counts", {})
    if not isinstance(revision_counts, dict):
        revision_counts = {}
    revision_key = f"{planned_step_id or 'adhoc-step'}|{latest_agent or 'unknown-agent'}"
    revision_attempts = int(revision_counts.get(revision_key, 0) or 0)
    recent_history = state.get("agent_history", [])[-8:]
    available_agents = [
        card.get("agent_name")
        for card in state.get("a2a", {}).get("agent_cards", [])
        if card.get("agent_name") and card.get("agent_name") != "reviewer_agent"
    ]
    if "worker_agent" not in available_agents and state.get("available_agents"):
        available_agents = [name for name in state["available_agents"] if name != "reviewer_agent"]
    allowed_next_agents = sorted(dict.fromkeys(available_agents))
    allowed_enum = "|".join(allowed_next_agents + ["finish"])
    allowed_text = ", ".join(allowed_next_agents) if allowed_next_agents else "worker_agent"
    latest_structured_context = {}
    if latest_agent == "local_drive_agent" and isinstance(state.get("local_drive_manifest"), dict):
        manifest = state.get("local_drive_manifest", {})
        latest_structured_context = {
            "folder_count": manifest.get("folder_count", 0),
            "file_count": manifest.get("file_count", 0),
            "selected_file_count": manifest.get("selected_file_count", 0),
            "excluded_file_count": manifest.get("excluded_file_count", 0),
            "truncated": bool(manifest.get("truncated", False)),
            "folders_preview": (manifest.get("folders") or [])[:5],
            "files_preview": (manifest.get("files") or [])[:10],
        }
    log_task_update(
        "Reviewer",
        f"Review pass #{state['reviewer_calls']} started. Auditing the latest step against the current objective.",
    )

    # --- Prompt tier selection based on model context window ---
    from kendr.llm_router import get_active_provider
    _provider = get_active_provider()
    _model = model_for_agent("reviewer_agent")
    _safe_tokens = _estimate_safe_context_tokens(_provider, _model)

    _prompt_args = (
        current_objective, state["user_query"], latest_agent,
        planned_step_id, planned_step_title, planned_step_success,
        revision_attempts, latest_output, recent_history, allowed_text,
    )

    _detailed = _build_detailed_prompt(*_prompt_args)
    _compact  = _build_compact_prompt(*_prompt_args)

    _detailed_tokens = len(_detailed) / 4
    _compact_tokens  = len(_compact)  / 4

    if _detailed_tokens <= _safe_tokens:
        prompt = _detailed
        log_task_update("Reviewer", f"Using detailed prompt (~{int(_detailed_tokens)} tokens, limit {_safe_tokens}).")
    elif _compact_tokens <= _safe_tokens:
        prompt = _compact
        log_task_update(
            "Reviewer",
            f"Model {_model!r} has limited context ({_safe_tokens} safe tokens). "
            f"Using compact prompt (~{int(_compact_tokens)} tokens).",
        )
    else:
        # Even compact prompt would overflow — surface a user-facing warning and stop cleanly.
        overflow_msg = (
            f"⚠️ Context overflow: the current model ({_model!r}) does not have "
            f"enough context window to run the reviewer agent "
            f"(estimated {int(_compact_tokens)} tokens needed, ~{_safe_tokens} available).\n\n"
            f"Please switch to a larger model, such as:\n"
            f"  • OpenAI: gpt-4o or gpt-4o-mini\n"
            f"  • Anthropic: claude-haiku-4-5, claude-sonnet-4-6\n"
            f"  • Ollama: llama3.1:8b or larger\n\n"
            f"You can change the model in Kendr settings."
        )
        log_task_update("Reviewer", f"Context overflow for {_model!r}. Notifying user.")
        # Set approve so the orchestrator exits the reviewer branch cleanly,
        # then force __finish__ so the run terminates with the warning as output.
        state["review_decision"] = "approve"
        state["review_reason"] = "Context overflow — run terminated."
        state["review_is_output_correct"] = False
        state["review_pending"] = False
        state["next_agent"] = "__finish__"
        state["final_output"] = overflow_msg
        state["workflow_status"] = "context_overflow"
        state["context_overflow_warning"] = overflow_msg
        state = publish_agent_output(
            state, "reviewer_agent", overflow_msg,
            f"reviewer_overflow_{state['reviewer_calls']}",
            recipients=["orchestrator_agent"],
        )
        return state

    response=llm.invoke(prompt)
    raw_output=normalize_llm_text(response.content if hasattr(response, "content") else response).strip()

    try:
        review_data = _parse_review_output(raw_output)
    except Exception:
        review_data = {
            "decision": "revise",
            "reason": "Reviewer returned invalid JSON. Retry the worker with the current objective.",
            "is_output_correct": False,
            "revised_objective": current_objective,
            "step_reviews": [
                {
                    "agent": latest_agent,
                    "status": "needs_revision",
                    "notes": "Reviewer output was invalid JSON.",
                }
            ],
            "next_agent": "worker_agent",
            "corrected_values": {},
        }

    decision = review_data.get("decision", "revise")
    reason = review_data.get("reason", "No reason provided")
    revised_objective = review_data.get("revised_objective") or current_objective
    next_agent = review_data.get("next_agent", "finish" if decision == "approve" else "worker_agent")
    if next_agent != "finish" and next_agent not in allowed_next_agents:
        next_agent = "worker_agent" if "worker_agent" in allowed_next_agents else "finish"
        reason = f"{reason} Reviewer fallback applied because the requested retry agent is not currently available."
    corrected_values = review_data.get("corrected_values", {})
    if not isinstance(corrected_values, dict):
        corrected_values = {}

    state["review_decision"] = decision
    state["review_reason"] = reason
    state["review_is_output_correct"] = bool(review_data.get("is_output_correct", decision == "approve"))
    state["review_step_assessments"] = review_data.get("step_reviews", [])
    state["review_target_agent"] = next_agent
    state["review_corrected_values"] = corrected_values
    state["review_revised_objective"] = revised_objective
    state["review_subject_step_id"] = planned_step_id
    state["review_subject_agent"] = latest_agent
    state["current_objective"] = revised_objective

    write_text_file(
    f"reviewer_output_{state['reviewer_calls']}.txt",
    raw_output
    + (
        f"\nParsed Decision: {decision}"
        f"\nReason: {reason}"
        f"\nRevised Objective: {revised_objective}"
        f"\nNext Agent: {next_agent}"
        f"\nCorrected Values: {json.dumps(corrected_values, ensure_ascii=False)}"
    )
    )
    log_task_update(
        "Reviewer",
        f"Decision saved to {OUTPUT_DIR}/reviewer_output_{state['reviewer_calls']}.txt",
        (
            f"Decision: {decision}\n"
            f"Reason: {reason}\n"
            f"Revised Objective: {revised_objective}\n"
            f"Next Agent: {next_agent}\n"
            f"Corrected Values: {json.dumps(corrected_values, ensure_ascii=False)}"
        ),
    )
    recipients = ["orchestrator_agent"]
    if decision == "revise" and next_agent != "finish":
        recipients.append(next_agent)
    state = publish_agent_output(
        state,
        "reviewer_agent",
        (
            f"Decision: {decision}\n"
            f"Reason: {reason}\n"
            f"Revised Objective: {revised_objective}\n"
            f"Next Agent: {next_agent}\n"
            f"Corrected Values: {json.dumps(corrected_values, ensure_ascii=False)}"
        ),
        f"reviewer_decision_{state['reviewer_calls']}",
        recipients=recipients,
    )
    return state
