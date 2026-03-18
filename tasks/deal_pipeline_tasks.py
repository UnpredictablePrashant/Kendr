import json
from pathlib import Path

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.research_infra import build_evidence_bundle, llm_json, llm_text, parse_documents, serp_search
from tasks.utils import OUTPUT_DIR, log_task_update, write_text_file


def _write_outputs(agent_name: str, call_number: int, summary: str, payload: dict):
    write_text_file(f"{agent_name}_{call_number}.txt", summary)
    write_text_file(f"{agent_name}_{call_number}.json", json.dumps(payload, indent=2, ensure_ascii=False))


def _resolve_paths(raw_paths, working_directory: str | None = None) -> list[str]:
    if isinstance(raw_paths, str):
        raw_paths = [raw_paths]
    results = []
    for raw_path in raw_paths or []:
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(working_directory or ".").resolve() / path
        results.append(str(path))
    return results


def _deal_evidence(state: dict) -> dict:
    evidence = build_evidence_bundle(state)
    evidence.update(
        {
            "prospect_list": state.get("prospect_list", []),
            "screened_prospects": state.get("screened_prospects", []),
            "sector_intelligence": state.get("sector_intelligence", {}),
            "meeting_brief": state.get("meeting_brief", {}),
            "investor_positioning": state.get("investor_positioning", {}),
            "financial_mis_analysis": state.get("financial_mis_analysis", {}),
            "deal_materials": state.get("deal_materials", {}),
            "investor_matches": state.get("investor_matches", []),
            "investor_outreach_plan": state.get("investor_outreach_plan", {}),
        }
    )
    return evidence


def prospect_identification_agent(state):
    _, task_content, _ = begin_agent_session(state, "prospect_identification_agent")
    state["prospect_identification_calls"] = state.get("prospect_identification_calls", 0) + 1
    call_number = state["prospect_identification_calls"]

    sectors = state.get("deal_sectors") or state.get("sector_focus") or [task_content or state.get("current_objective") or state.get("user_query", "")]
    if isinstance(sectors, str):
        sectors = [sectors]
    stages = state.get("fundraising_stages") or ["Series A", "Series B"]
    geography = state.get("deal_geography", "")

    search_queries = [
        f"{sector} startups raised {' or '.join(stages)} {geography}".strip()
        for sector in sectors[:3]
    ]
    search_payloads = [serp_search(query, num=int(state.get("prospect_search_results", 8))) for query in search_queries if query.strip()]

    prompt = f"""
You are a deal sourcing agent.

Goal:
Identify client prospects in the requested sectors and filter for companies that have raised Series A or Series B.

Sectors:
{json.dumps(sectors, ensure_ascii=False)}

Stages:
{json.dumps(stages, ensure_ascii=False)}

Geography:
{geography or "Any"}

Search evidence:
{json.dumps(search_payloads, indent=2, ensure_ascii=False)[:30000]}

Return ONLY valid JSON:
{{
  "prospects": [
    {{
      "company": "company name",
      "sector": "sector",
      "funding_stage": "Series A or Series B",
      "amount_raised": "amount if known",
      "date": "funding date if known",
      "geography": "country/region",
      "why_relevant": "why this prospect matters"
    }}
  ],
  "summary": "brief sourcing summary"
}}
"""
    result = llm_json(prompt, {"prospects": [], "summary": "No prospects identified."})
    summary = result.get("summary", "No prospects identified.")
    _write_outputs("prospect_identification_agent", call_number, summary, result)
    state["prospect_search_payloads"] = search_payloads
    state["prospect_list"] = result.get("prospects", [])
    state["draft_response"] = summary
    log_task_update("Prospect Identification", f"Prospect pass #{call_number} saved to {OUTPUT_DIR}/prospect_identification_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "prospect_identification_agent",
        summary,
        f"prospect_identification_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def funding_stage_screening_agent(state):
    _, task_content, _ = begin_agent_session(state, "funding_stage_screening_agent")
    state["funding_stage_screening_calls"] = state.get("funding_stage_screening_calls", 0) + 1
    call_number = state["funding_stage_screening_calls"]
    prospects = state.get("prospect_list", [])
    criteria = state.get("screening_criteria") or task_content or "Prefer strong Series A and Series B candidates with clear fit."

    prompt = f"""
You are a funding-stage screening agent.

Screen and rank the sourced prospects against the mandate.

Criteria:
{criteria}

Prospects:
{json.dumps(prospects, indent=2, ensure_ascii=False)}

Return ONLY valid JSON:
{{
  "screened_prospects": [
    {{
      "company": "company name",
      "fit_score": 0,
      "screening_reason": "why shortlisted",
      "priority": "high|medium|low"
    }}
  ],
  "summary": "brief screening summary"
}}
"""
    result = llm_json(prompt, {"screened_prospects": [], "summary": "No screening summary."})
    summary = result.get("summary", "No screening summary.")
    _write_outputs("funding_stage_screening_agent", call_number, summary, result)
    state["screened_prospects"] = result.get("screened_prospects", [])
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "funding_stage_screening_agent",
        summary,
        f"funding_stage_screening_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def sector_intelligence_agent(state):
    _, task_content, _ = begin_agent_session(state, "sector_intelligence_agent")
    state["sector_intelligence_calls"] = state.get("sector_intelligence_calls", 0) + 1
    call_number = state["sector_intelligence_calls"]
    sector = state.get("deal_sector") or state.get("sector_focus") or task_content or state.get("current_objective") or state.get("user_query", "")

    search_payload = serp_search(f"{sector} market trends revenue benchmarks growth drivers", num=int(state.get("sector_search_results", 8)))
    prompt = f"""
You are a sector intelligence agent for fundraising and advisory work.

Sector:
{sector}

Search evidence:
{json.dumps(search_payload, indent=2, ensure_ascii=False)[:30000]}

Return ONLY valid JSON:
{{
  "sector": "{sector}",
  "market_size_view": "brief view",
  "revenue_models": ["model"],
  "past_trends": ["trend"],
  "micro_trends": ["micro trend"],
  "benchmarks": ["benchmark"],
  "summary": "brief sector summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "sector": sector,
            "market_size_view": "",
            "revenue_models": [],
            "past_trends": [],
            "micro_trends": [],
            "benchmarks": [],
            "summary": "No sector summary generated.",
        },
    )
    summary = result.get("summary", "No sector summary generated.")
    _write_outputs("sector_intelligence_agent", call_number, summary, result)
    state["sector_search_payload"] = search_payload
    state["sector_intelligence"] = result
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "sector_intelligence_agent",
        summary,
        f"sector_intelligence_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def company_meeting_brief_agent(state):
    _, task_content, _ = begin_agent_session(state, "company_meeting_brief_agent")
    state["company_meeting_brief_calls"] = state.get("company_meeting_brief_calls", 0) + 1
    call_number = state["company_meeting_brief_calls"]
    target_company = state.get("company_name") or state.get("research_target") or task_content or state.get("current_objective") or state.get("user_query", "")
    evidence = _deal_evidence(state)

    prompt = f"""
You are a company meeting preparation agent for an advisory and fundraising workflow.

Target company:
{target_company}

Evidence:
{json.dumps(evidence, indent=2, ensure_ascii=False)[:32000]}

Prepare a meeting brief that helps impress the client and frame the Unitus point of view.

Return ONLY valid JSON:
{{
  "company": "{target_company}",
  "meeting_objective": "what the meeting should achieve",
  "company_snapshot": "brief company understanding",
  "unitus_view": "how Unitus should position itself",
  "questions_to_ask": ["question"],
  "impression_points": ["point"],
  "summary": "brief meeting summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "company": target_company,
            "meeting_objective": "",
            "company_snapshot": "",
            "unitus_view": "",
            "questions_to_ask": [],
            "impression_points": [],
            "summary": "No meeting brief generated.",
        },
    )
    summary = result.get("summary", "No meeting brief generated.")
    _write_outputs("company_meeting_brief_agent", call_number, summary, result)
    state["meeting_brief"] = result
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "company_meeting_brief_agent",
        summary,
        f"company_meeting_brief_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def investor_positioning_agent(state):
    _, task_content, _ = begin_agent_session(state, "investor_positioning_agent")
    state["investor_positioning_calls"] = state.get("investor_positioning_calls", 0) + 1
    call_number = state["investor_positioning_calls"]
    evidence = _deal_evidence(state)
    mandate = task_content or state.get("current_objective") or state.get("user_query", "")

    prompt = f"""
You are an investor positioning agent.

Mandate:
{mandate}

Evidence:
{json.dumps(evidence, indent=2, ensure_ascii=False)[:32000]}

Determine what kind of investors the company should target and how the story should be positioned.

Return ONLY valid JSON:
{{
  "ideal_investor_types": ["investor type"],
  "investment_story": "core narrative",
  "differentiators": ["point"],
  "proof_points": ["point"],
  "risks_to_address": ["risk"],
  "summary": "brief investor positioning summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "ideal_investor_types": [],
            "investment_story": "",
            "differentiators": [],
            "proof_points": [],
            "risks_to_address": [],
            "summary": "No investor positioning summary generated.",
        },
    )
    summary = result.get("summary", "No investor positioning summary generated.")
    _write_outputs("investor_positioning_agent", call_number, summary, result)
    state["investor_positioning"] = result
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "investor_positioning_agent",
        summary,
        f"investor_positioning_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def financial_mis_analysis_agent(state):
    _, task_content, _ = begin_agent_session(state, "financial_mis_analysis_agent")
    state["financial_mis_analysis_calls"] = state.get("financial_mis_analysis_calls", 0) + 1
    call_number = state["financial_mis_analysis_calls"]

    raw_paths = state.get("financial_document_paths") or state.get("document_paths") or []
    paths = _resolve_paths(raw_paths, state.get("financial_working_directory"))
    documents = parse_documents(paths) if paths else state.get("documents", [])
    excel_summary = state.get("excel_summary_text") or json.dumps(state.get("excel_workbook_summary", {}), ensure_ascii=False)

    prompt = f"""
You are a financial and MIS analysis agent.

Objective:
{task_content or state.get("current_objective") or state.get("user_query", "")}

Documents:
{json.dumps(documents, indent=2, ensure_ascii=False)[:22000]}

Excel/MIS summary:
{excel_summary[:12000] if isinstance(excel_summary, str) else str(excel_summary)}

Return ONLY valid JSON:
{{
  "key_metrics": ["metric"],
  "performance_observations": ["observation"],
  "mis_gaps": ["gap"],
  "red_flags": ["risk"],
  "follow_up_requests": ["request"],
  "summary": "brief financial analysis summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "key_metrics": [],
            "performance_observations": [],
            "mis_gaps": [],
            "red_flags": [],
            "follow_up_requests": [],
            "summary": "No financial analysis summary generated.",
        },
    )
    summary = result.get("summary", "No financial analysis summary generated.")
    _write_outputs("financial_mis_analysis_agent", call_number, summary, result)
    state["financial_documents"] = documents
    state["financial_mis_analysis"] = result
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "financial_mis_analysis_agent",
        summary,
        f"financial_mis_analysis_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )


def deal_materials_agent(state):
    _, task_content, _ = begin_agent_session(state, "deal_materials_agent")
    state["deal_materials_calls"] = state.get("deal_materials_calls", 0) + 1
    call_number = state["deal_materials_calls"]
    evidence = _deal_evidence(state)

    prompt = f"""
You are a deal materials preparation agent.

Prepare the content structure needed for:
- an Excel workplan/model
- a PPT/deck storyline
- an opportunity memo

Task:
{task_content or state.get("current_objective") or state.get("user_query", "")}

Evidence:
{json.dumps(evidence, indent=2, ensure_ascii=False)[:32000]}

Return ONLY valid JSON:
{{
  "excel_workplan": ["worksheet or analysis block"],
  "ppt_storyline": ["slide title"],
  "opportunity_memo_sections": ["section"],
  "deliverable_recommendation": "what should be sent first",
  "summary": "brief materials summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "excel_workplan": [],
            "ppt_storyline": [],
            "opportunity_memo_sections": [],
            "deliverable_recommendation": "",
            "summary": "No materials summary generated.",
        },
    )
    summary = result.get("summary", "No materials summary generated.")
    _write_outputs("deal_materials_agent", call_number, summary, result)
    state["deal_materials"] = result
    state["report_requirement"] = (
        "Create a downloadable advisory report in pdf, html, and xlsx format covering prospect screening, sector intelligence, company diligence, investor positioning, investor list, and deliverables."
    )
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "deal_materials_agent",
        summary,
        f"deal_materials_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )


def investor_matching_agent(state):
    _, task_content, _ = begin_agent_session(state, "investor_matching_agent")
    state["investor_matching_calls"] = state.get("investor_matching_calls", 0) + 1
    call_number = state["investor_matching_calls"]
    sector = state.get("deal_sector") or state.get("sector_focus") or ""
    geography = state.get("deal_geography", "")
    stage = ", ".join(state.get("fundraising_stages", ["Series A", "Series B"]))
    query = state.get("investor_query") or f"{sector} investors {stage} {geography}".strip()
    search_payload = serp_search(query, num=int(state.get("investor_search_results", 10)))
    evidence = _deal_evidence(state)
    evidence["investor_search_payload"] = search_payload

    prompt = f"""
You are an investor matching agent.

Goal:
Find the right set of investors for the company and mandate.

Query:
{query}

Evidence:
{json.dumps(evidence, indent=2, ensure_ascii=False)[:32000]}

Return ONLY valid JSON:
{{
  "investors": [
    {{
      "investor_name": "name",
      "investor_type": "vc|family office|impact|growth|strategic|other",
      "sector_fit": "why they fit the sector",
      "stage_fit": "why they fit the raise stage",
      "geography_fit": "geography fit",
      "priority": "high|medium|low"
    }}
  ],
  "summary": "brief investor matching summary"
}}
"""
    result = llm_json(prompt, {"investors": [], "summary": "No investor matches generated."})
    summary = result.get("summary", "No investor matches generated.")
    _write_outputs("investor_matching_agent", call_number, summary, result)
    state["investor_search_payload"] = search_payload
    state["investor_matches"] = result.get("investors", [])
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "investor_matching_agent",
        summary,
        f"investor_matching_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent"],
    )


def investor_outreach_agent(state):
    _, task_content, _ = begin_agent_session(state, "investor_outreach_agent")
    state["investor_outreach_calls"] = state.get("investor_outreach_calls", 0) + 1
    call_number = state["investor_outreach_calls"]
    evidence = _deal_evidence(state)

    prompt = f"""
You are an investor outreach planning agent.

Task:
{task_content or state.get("current_objective") or state.get("user_query", "")}

Evidence:
{json.dumps(evidence, indent=2, ensure_ascii=False)[:32000]}

Build a practical outreach plan for the shortlisted investors.

Return ONLY valid JSON:
{{
  "priority_sequence": ["investor or investor cluster"],
  "warm_intro_strategy": ["step"],
  "cold_outreach_angles": ["angle"],
  "artifacts_to_send": ["artifact"],
  "summary": "brief outreach summary"
}}
"""
    result = llm_json(
        prompt,
        {
            "priority_sequence": [],
            "warm_intro_strategy": [],
            "cold_outreach_angles": [],
            "artifacts_to_send": [],
            "summary": "No outreach summary generated.",
        },
    )
    summary = result.get("summary", "No outreach summary generated.")
    _write_outputs("investor_outreach_agent", call_number, summary, result)
    state["investor_outreach_plan"] = result
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "investor_outreach_agent",
        summary,
        f"investor_outreach_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )
