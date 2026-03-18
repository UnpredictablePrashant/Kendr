import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.utils import OUTPUT_DIR, log_task_update, write_text_file


SERP_API_URL = "https://serpapi.com/search.json"


def _format_search_summary(query: str, payload: dict, max_results: int) -> str:
    lines = [f"Google Search Query: {query}", ""]

    search_metadata = payload.get("search_metadata", {})
    search_parameters = payload.get("search_parameters", {})
    answer_box = payload.get("answer_box")
    knowledge_graph = payload.get("knowledge_graph")
    organic_results = payload.get("organic_results", [])
    related_questions = payload.get("related_questions", [])

    lines.append(f"Status: {search_metadata.get('status', 'unknown')}")
    lines.append(f"Engine: {search_parameters.get('engine', 'google')}")
    lines.append("")

    if answer_box:
        lines.append("Answer Box:")
        answer_title = answer_box.get("title") or answer_box.get("type") or "Direct answer"
        answer_value = (
            answer_box.get("answer")
            or answer_box.get("snippet")
            or answer_box.get("result")
            or answer_box.get("displayed_link")
            or "No direct answer text returned."
        )
        lines.append(f"- {answer_title}: {answer_value}")
        lines.append("")

    if knowledge_graph:
        lines.append("Knowledge Graph:")
        kg_title = knowledge_graph.get("title") or "Knowledge graph"
        kg_description = knowledge_graph.get("description") or "No description returned."
        lines.append(f"- {kg_title}: {kg_description}")
        lines.append("")

    lines.append("Top Organic Results:")
    if not organic_results:
        lines.append("- No organic results returned.")
    else:
        for index, result in enumerate(organic_results[:max_results], start=1):
            title = result.get("title") or "Untitled result"
            link = result.get("link") or "No link returned"
            snippet = result.get("snippet") or "No snippet returned."
            lines.append(f"{index}. {title}")
            lines.append(f"   Link: {link}")
            lines.append(f"   Snippet: {snippet}")

    if related_questions:
        lines.append("")
        lines.append("Related Questions:")
        for question in related_questions[:3]:
            question_text = question.get("question") or "Unknown question"
            snippet = question.get("snippet") or "No snippet returned."
            lines.append(f"- {question_text}")
            lines.append(f"  {snippet}")

    if payload.get("error"):
        lines.append("")
        lines.append(f"API Error: {payload['error']}")

    return "\n".join(lines).strip()


def google_search_agent(state):
    active_task, task_content, _ = begin_agent_session(state, "google_search_agent")
    state["google_search_calls"] = state.get("google_search_calls", 0) + 1

    query = state.get("search_query") or task_content or state.get("current_objective") or state.get("user_query", "").strip()
    if not query:
        raise ValueError("google_search_agent requires 'search_query' or 'user_query' in state.")

    api_key = os.getenv("SERP_API_KEY")
    if not api_key:
        raise ValueError("SERP_API_KEY is not set. Add it to .env before running google_search_agent.")

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "hl": state.get("search_hl", "en"),
        "gl": state.get("search_gl", "us"),
        "num": int(state.get("search_num", 5)),
    }

    if state.get("search_location"):
        params["location"] = state["search_location"]
    if state.get("search_start") is not None:
        params["start"] = int(state["search_start"])
    if state.get("search_safe"):
        params["safe"] = state["search_safe"]

    request_url = f"{SERP_API_URL}?{urlencode(params)}"
    call_number = state["google_search_calls"]

    log_task_update("Google Search", f"Search pass #{call_number} started.")
    log_task_update(
        "Google Search",
        "Querying SerpAPI Google Search with the configured parameters.",
        f"Query: {query}",
    )

    with urlopen(request_url, timeout=int(state.get("search_timeout", 30))) as response:
        payload = json.loads(response.read().decode("utf-8"))

    summary = _format_search_summary(query, payload, params["num"])
    summary_filename = f"google_search_output_{call_number}.txt"
    raw_filename = f"google_search_raw_{call_number}.json"

    write_text_file(summary_filename, summary)
    write_text_file(raw_filename, json.dumps(payload, indent=2, ensure_ascii=False))

    state["search_query"] = query
    state["search_results"] = payload
    state["search_summary"] = summary
    state["draft_response"] = summary

    log_task_update(
        "Google Search",
        f"Search results saved to {OUTPUT_DIR}/{summary_filename} and {OUTPUT_DIR}/{raw_filename}.",
        summary,
    )
    state = publish_agent_output(
        state,
        "google_search_agent",
        summary,
        f"google_search_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent"],
    )
    return state
