import json
from pathlib import Path

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.research_infra import (
    build_evidence_bundle,
    evidence_text,
    llm_json,
    openalex_search,
    parse_documents,
    serp_patent_search,
    serp_scholar_search,
)
from tasks.utils import OUTPUT_DIR, log_task_update, write_text_file


def _write_outputs(agent_name: str, call_number: int, summary: str, payload: dict):
    write_text_file(f"{agent_name}_{call_number}.txt", summary)
    write_text_file(f"{agent_name}_{call_number}.json", json.dumps(payload, indent=2, ensure_ascii=False))


def _resolve_paths(raw_paths, working_directory: str | None = None) -> list[str]:
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    paths = []
    for raw_path in raw_paths or []:
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(working_directory or ".").resolve() / path
        paths.append(str(path))
    return paths


def literature_search_agent(state):
    _, task_content, _ = begin_agent_session(state, "literature_search_agent")
    state["literature_search_calls"] = state.get("literature_search_calls", 0) + 1
    call_number = state["literature_search_calls"]
    query = state.get("literature_query") or task_content or state.get("current_objective") or state.get("user_query", "")
    if not query:
        raise ValueError("literature_search_agent requires a literature query.")

    openalex_payload = openalex_search(query, per_page=int(state.get("literature_openalex_results", 10)))
    scholar_payload = None
    if state.get("use_scholar_search", True):
        scholar_payload = serp_scholar_search(query, num=int(state.get("literature_scholar_results", 10)))

    prompt = f"""
You are a research literature search agent.

Query:
{query}

OpenAlex results:
{json.dumps(openalex_payload, indent=2, ensure_ascii=False)[:30000]}

Google Scholar results:
{json.dumps(scholar_payload, indent=2, ensure_ascii=False)[:25000] if scholar_payload else "Not used."}

Return ONLY valid JSON:
{{
  "papers": [
    {{
      "title": "paper title",
      "authors": ["author"],
      "year": 2024,
      "source": "journal or archive",
      "url": "url",
      "why_relevant": "brief reason"
    }}
  ],
  "themes": ["theme"],
  "gaps": ["gap"],
  "summary": "brief literature summary"
}}
"""
    result = llm_json(prompt, {"papers": [], "themes": [], "gaps": [], "summary": "No literature summary generated."})
    summary = result.get("summary", "No literature summary generated.")
    payload = {"query": query, "openalex": openalex_payload, "scholar": scholar_payload, "analysis": result}
    _write_outputs("literature_search_agent", call_number, summary, payload)
    state["literature_results"] = result
    state["literature_raw"] = payload
    state["draft_response"] = summary
    log_task_update("Literature Search", f"Literature pass #{call_number} saved to {OUTPUT_DIR}/literature_search_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "literature_search_agent",
        summary,
        f"literature_search_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def patent_search_agent(state):
    _, task_content, _ = begin_agent_session(state, "patent_search_agent")
    state["patent_search_calls"] = state.get("patent_search_calls", 0) + 1
    call_number = state["patent_search_calls"]
    query = state.get("patent_query") or task_content or state.get("current_objective") or state.get("user_query", "")
    if not query:
        raise ValueError("patent_search_agent requires a patent query.")

    patents_payload = serp_patent_search(query, num=int(state.get("patent_search_results", 10)))

    prompt = f"""
You are a patent search agent.

Query:
{query}

Patent search results:
{json.dumps(patents_payload, indent=2, ensure_ascii=False)[:30000]}

Return ONLY valid JSON:
{{
  "patents": [
    {{
      "title": "patent title",
      "patent_number": "number if visible",
      "assignee": "assignee",
      "year": "year if visible",
      "url": "url",
      "why_relevant": "brief reason"
    }}
  ],
  "technical_clusters": ["cluster"],
  "summary": "brief patent landscape summary"
}}
"""
    result = llm_json(prompt, {"patents": [], "technical_clusters": [], "summary": "No patent summary generated."})
    summary = result.get("summary", "No patent summary generated.")
    payload = {"query": query, "raw": patents_payload, "analysis": result}
    _write_outputs("patent_search_agent", call_number, summary, payload)
    state["patent_results"] = result
    state["patent_raw"] = payload
    state["draft_response"] = summary
    log_task_update("Patent Search", f"Patent pass #{call_number} saved to {OUTPUT_DIR}/patent_search_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "patent_search_agent",
        summary,
        f"patent_search_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def proposal_review_agent(state):
    _, task_content, _ = begin_agent_session(state, "proposal_review_agent")
    state["proposal_review_calls"] = state.get("proposal_review_calls", 0) + 1
    call_number = state["proposal_review_calls"]
    raw_paths = state.get("proposal_document_paths") or state.get("document_paths") or []
    paths = _resolve_paths(raw_paths, state.get("proposal_working_directory"))
    if not paths and task_content and Path(task_content).exists():
        paths = [task_content]
    if not paths:
        raise ValueError("proposal_review_agent requires 'proposal_document_paths' or a document path task.")

    documents = parse_documents(paths)
    prompt = f"""
You are a research proposal review agent.

Review the proposal documents and extract the key problem, objectives, novelty claims, methods, assumptions, deliverables, risks, and open questions.

Documents:
{json.dumps(documents, indent=2, ensure_ascii=False)[:32000]}

Return ONLY valid JSON:
{{
  "proposal_title": "title if available",
  "problem_statement": "problem",
  "objectives": ["objective"],
  "novelty_claims": ["claim"],
  "methods": ["method"],
  "deliverables": ["deliverable"],
  "risks_or_gaps": ["risk"],
  "questions_for_authors": ["question"],
  "summary": "brief proposal summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "proposal_title": "",
            "problem_statement": "",
            "objectives": [],
            "novelty_claims": [],
            "methods": [],
            "deliverables": [],
            "risks_or_gaps": [],
            "questions_for_authors": [],
            "summary": "No proposal summary generated.",
        },
    )
    summary = result.get("summary", "No proposal summary generated.")
    payload = {"documents": documents, "analysis": result}
    _write_outputs("proposal_review_agent", call_number, summary, payload)
    state["proposal_documents"] = documents
    state["proposal_review"] = result
    state["draft_response"] = summary
    log_task_update("Proposal Review", f"Proposal pass #{call_number} saved to {OUTPUT_DIR}/proposal_review_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "proposal_review_agent",
        summary,
        f"proposal_review_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def prior_art_analysis_agent(state):
    _, task_content, _ = begin_agent_session(state, "prior_art_analysis_agent")
    state["prior_art_analysis_calls"] = state.get("prior_art_analysis_calls", 0) + 1
    call_number = state["prior_art_analysis_calls"]
    evidence = build_evidence_bundle(state)
    evidence.update(
        {
            "proposal_review": state.get("proposal_review", {}),
            "literature_results": state.get("literature_results", {}),
            "patent_results": state.get("patent_results", {}),
        }
    )

    prompt = f"""
You are a prior-art analysis agent.

Goal:
Compare the proposal against known literature and patents, then assess novelty overlap, white space, and obvious prior-art risk.

Focus:
{task_content or state.get("current_objective") or state.get("user_query", "")}

Evidence:
{evidence_text(evidence)}

Return ONLY valid JSON:
{{
  "overlap_findings": ["overlap finding"],
  "novelty_support": ["support point"],
  "prior_art_risks": ["risk"],
  "white_space_areas": ["white space"],
  "recommended_next_checks": ["check"],
  "summary": "brief prior-art summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "overlap_findings": [],
            "novelty_support": [],
            "prior_art_risks": [],
            "white_space_areas": [],
            "recommended_next_checks": [],
            "summary": "No prior-art summary generated.",
        },
    )
    summary = result.get("summary", "No prior-art summary generated.")
    _write_outputs("prior_art_analysis_agent", call_number, summary, result)
    state["prior_art_analysis"] = result
    state["draft_response"] = summary
    log_task_update("Prior Art", f"Prior-art pass #{call_number} saved to {OUTPUT_DIR}/prior_art_analysis_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "prior_art_analysis_agent",
        summary,
        f"prior_art_analysis_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def claim_evidence_mapping_agent(state):
    _, task_content, _ = begin_agent_session(state, "claim_evidence_mapping_agent")
    state["claim_evidence_mapping_calls"] = state.get("claim_evidence_mapping_calls", 0) + 1
    call_number = state["claim_evidence_mapping_calls"]

    claims = state.get("claims_to_verify") or state.get("proposal_review", {}).get("novelty_claims", [])
    evidence = build_evidence_bundle(state)
    evidence.update(
        {
            "proposal_review": state.get("proposal_review", {}),
            "literature_results": state.get("literature_results", {}),
            "patent_results": state.get("patent_results", {}),
            "prior_art_analysis": state.get("prior_art_analysis", {}),
        }
    )

    prompt = f"""
You are a claim-to-evidence mapping agent.

Claims:
{json.dumps(claims, indent=2, ensure_ascii=False)}

Evidence:
{evidence_text(evidence)}

Return ONLY valid JSON:
{{
  "claim_map": [
    {{
      "claim": "claim text",
      "supporting_evidence": ["evidence item"],
      "contradicting_evidence": ["evidence item"],
      "confidence": "low|medium|high",
      "notes": "brief note"
    }}
  ],
  "summary": "brief evidence-mapping summary"
}}
"""
    result = llm_json(prompt, {"claim_map": [], "summary": "No evidence mapping summary generated."})
    summary = result.get("summary", "No evidence mapping summary generated.")
    _write_outputs("claim_evidence_mapping_agent", call_number, summary, result)
    state["claim_evidence_map"] = result
    state["draft_response"] = summary
    log_task_update("Claim Mapping", f"Claim-mapping pass #{call_number} saved to {OUTPUT_DIR}/claim_evidence_mapping_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "claim_evidence_mapping_agent",
        summary,
        f"claim_evidence_mapping_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )
