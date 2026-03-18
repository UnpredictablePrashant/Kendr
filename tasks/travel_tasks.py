import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.research_infra import llm_text
from tasks.utils import log_task_update, write_text_file


SERP_API_URL = "https://serpapi.com/search.json"


def _serpapi_request(params: dict, timeout: int = 45) -> dict:
    api_key = os.getenv("SERP_API_KEY", "").strip()
    if not api_key:
        raise ValueError("SERP_API_KEY is required for travel agents.")
    payload = {**params, "api_key": api_key}
    url = f"{SERP_API_URL}?{urlencode(payload)}"
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _write_outputs(agent_name: str, call_number: int, summary: str, payload: dict):
    write_text_file(f"{agent_name}_{call_number}.txt", summary)
    write_text_file(f"{agent_name}_{call_number}.json", json.dumps(payload, indent=2, ensure_ascii=False))


def _travel_mode_code(mode: str) -> str:
    normalized = (mode or "transit").strip().lower()
    mapping = {
        "driving": "0",
        "cycling": "1",
        "walking": "2",
        "transit": "3",
        "flight": "4",
        "best": "6",
        "two_wheeler": "9",
        "bike": "1",
        "car": "0",
        "train": "3",
        "bus": "3",
    }
    return mapping.get(normalized, "3")


def flight_tracking_agent(state):
    _, _, _ = begin_agent_session(state, "flight_tracking_agent")
    state["flight_tracking_calls"] = state.get("flight_tracking_calls", 0) + 1
    call_number = state["flight_tracking_calls"]

    departure_id = state.get("flight_departure_id") or state.get("travel_origin_code")
    arrival_id = state.get("flight_arrival_id") or state.get("travel_destination_code")
    outbound_date = state.get("flight_outbound_date")
    return_date = state.get("flight_return_date")
    if not (departure_id and arrival_id and outbound_date):
        raise ValueError(
            "flight_tracking_agent requires flight_departure_id, flight_arrival_id, and flight_outbound_date."
        )

    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "hl": state.get("travel_hl", "en"),
        "gl": state.get("travel_gl", "us"),
        "currency": state.get("travel_currency", "USD"),
        "type": str(state.get("flight_type", 1 if return_date else 2)),
        "travel_class": str(state.get("flight_travel_class", 1)),
        "adults": int(state.get("flight_adults", 1)),
        "children": int(state.get("flight_children", 0)),
        "sort_by": str(state.get("flight_sort_by", 1)),
        "stops": str(state.get("flight_stops", 0)),
    }
    if return_date:
        params["return_date"] = return_date
    if state.get("flight_deep_search") is not None:
        params["deep_search"] = "true" if state["flight_deep_search"] else "false"

    log_task_update(
        "Flight Tracking",
        f"Flight pass #{call_number} started.",
        f"{departure_id} -> {arrival_id} on {outbound_date}",
    )
    payload = _serpapi_request(params, timeout=int(state.get("flight_timeout", 45)))
    summary = llm_text(
        f"""You are a flight tracking and travel planning agent.

Summarize these flight results in a practical way.
Highlight:
- best options
- cheapest and fastest tradeoffs
- nonstop vs stopover observations
- relevant airlines, timings, and price cues
- anything worth flagging to the traveler

Flight payload:
{json.dumps(payload, indent=2, ensure_ascii=False)[:30000]}
"""
    )
    _write_outputs("flight_tracking_agent", call_number, summary, payload)
    state["flight_results"] = payload
    state["flight_summary"] = summary
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "flight_tracking_agent",
        summary,
        f"flight_tracking_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )


def transport_route_agent(state):
    _, _, _ = begin_agent_session(state, "transport_route_agent")
    state["transport_route_calls"] = state.get("transport_route_calls", 0) + 1
    call_number = state["transport_route_calls"]

    start_addr = state.get("route_start_addr") or state.get("travel_origin") or state.get("location_query")
    end_addr = state.get("route_end_addr") or state.get("travel_destination")
    start_coords = state.get("route_start_coords")
    end_coords = state.get("route_end_coords")
    if not ((start_addr or start_coords) and (end_addr or end_coords)):
        raise ValueError(
            "transport_route_agent requires route_start_addr/route_start_coords and route_end_addr/route_end_coords."
        )

    travel_mode = state.get("transport_mode") or state.get("route_travel_mode") or "transit"
    params = {
        "engine": "google_maps_directions",
        "hl": state.get("travel_hl", "en"),
        "travel_mode": _travel_mode_code(travel_mode),
    }
    if start_addr:
        params["start_addr"] = start_addr
    if end_addr:
        params["end_addr"] = end_addr
    if start_coords:
        params["start_coords"] = start_coords
    if end_coords:
        params["end_coords"] = end_coords
    if state.get("route_prefer"):
        params["prefer"] = state["route_prefer"]
    if state.get("route_option"):
        params["route"] = str(state["route_option"])
    if state.get("route_time"):
        params["time"] = state["route_time"]
    if state.get("route_avoid"):
        params["avoid"] = state["route_avoid"]
    if state.get("route_distance_unit") is not None:
        params["distance_unit"] = str(state["route_distance_unit"])

    log_task_update(
        "Transport Route",
        f"Route pass #{call_number} started.",
        f"{start_addr or start_coords} -> {end_addr or end_coords} via {travel_mode}",
    )
    payload = _serpapi_request(params, timeout=int(state.get("route_timeout", 45)))
    summary = llm_text(
        f"""You are a transport routing agent.

Summarize these route and transit results in a practical way.
Highlight:
- best route options
- train, bus, transit, driving, walking, cycling, or flight observations as relevant
- timing, transfers, costs, and duration tradeoffs
- useful travel guidance or caveats

Route payload:
{json.dumps(payload, indent=2, ensure_ascii=False)[:30000]}
"""
    )
    _write_outputs("transport_route_agent", call_number, summary, payload)
    state["transport_route_results"] = payload
    state["transport_route_summary"] = summary
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "transport_route_agent",
        summary,
        f"transport_route_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )


def travel_hub_agent(state):
    _, task_content, _ = begin_agent_session(state, "travel_hub_agent")
    state["travel_hub_calls"] = state.get("travel_hub_calls", 0) + 1
    call_number = state["travel_hub_calls"]

    payload = {
        "task": task_content or state.get("current_objective") or state.get("user_query", ""),
        "flight_results": state.get("flight_results", {}),
        "flight_summary": state.get("flight_summary", ""),
        "transport_route_results": state.get("transport_route_results", {}),
        "transport_route_summary": state.get("transport_route_summary", ""),
    }
    summary = llm_text(
        f"""You are a travel synthesis agent.

Combine these travel outputs into one concise answer.
Explain the overall best choice, notable tradeoffs, and any timing or routing risks.

Travel payload:
{json.dumps(payload, indent=2, ensure_ascii=False)[:30000]}
"""
    )
    _write_outputs("travel_hub_agent", call_number, summary, payload)
    state["travel_hub_results"] = payload
    state["travel_hub_summary"] = summary
    state["draft_response"] = summary
    return publish_agent_output(
        state,
        "travel_hub_agent",
        summary,
        f"travel_hub_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )
