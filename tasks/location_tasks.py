import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.research_infra import llm_text
from tasks.utils import OUTPUT_DIR, log_task_update, write_text_file


NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _user_agent() -> str:
    return os.getenv("RESEARCH_USER_AGENT", "multi-agent-research-bot/1.0 (+https://localhost)")


def _http_json(url: str, *, method: str = "GET", data: bytes | None = None, timeout: int = 30, headers: dict | None = None):
    merged_headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    request = Request(url, headers=merged_headers, method=method, data=data)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _nominatim_search(query: str, limit: int = 5, countrycodes: str | None = None) -> list[dict]:
    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "namedetails": 1,
        "extratags": 1,
        "limit": limit,
    }
    if countrycodes:
        params["countrycodes"] = countrycodes
    return _http_json(f"{NOMINATIM_SEARCH_URL}?{urlencode(params)}")


def _nominatim_reverse(lat: float, lon: float) -> dict:
    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "addressdetails": 1,
        "extratags": 1,
        "namedetails": 1,
    }
    return _http_json(f"{NOMINATIM_REVERSE_URL}?{urlencode(params)}")


def _overpass_nearby(lat: float, lon: float, radius_meters: int, amenities: list[str] | None = None, limit: int = 25) -> list[dict]:
    amenities = amenities or ["school", "hospital", "bank", "pharmacy", "restaurant", "bus_station", "fuel"]
    amenity_regex = "|".join(sorted({item.strip() for item in amenities if item and item.strip()}))
    if not amenity_regex:
        amenity_regex = "school|hospital|bank|pharmacy|restaurant|bus_station|fuel"

    query = f"""
[out:json][timeout:25];
(
  node["amenity"~"^({amenity_regex})$"](around:{radius_meters},{lat},{lon});
  way["amenity"~"^({amenity_regex})$"](around:{radius_meters},{lat},{lon});
  relation["amenity"~"^({amenity_regex})$"](around:{radius_meters},{lat},{lon});
);
out center {limit};
""".strip()
    payload = _http_json(
        OVERPASS_URL,
        method="POST",
        data=query.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        timeout=45,
    )
    results = []
    for item in payload.get("elements", [])[:limit]:
        tags = item.get("tags", {})
        center = item.get("center", {})
        results.append(
            {
                "type": item.get("type"),
                "id": item.get("id"),
                "name": tags.get("name", ""),
                "amenity": tags.get("amenity", ""),
                "shop": tags.get("shop", ""),
                "tourism": tags.get("tourism", ""),
                "lat": item.get("lat", center.get("lat")),
                "lon": item.get("lon", center.get("lon")),
                "tags": tags,
            }
        )
    return results


def location_agent(state):
    _, task_content, _ = begin_agent_session(state, "location_agent")
    state["location_agent_calls"] = state.get("location_agent_calls", 0) + 1
    call_number = state["location_agent_calls"]

    query = state.get("location_query") or state.get("place_query") or task_content or state.get("current_objective") or state.get("user_query", "")
    lat = state.get("location_lat")
    lon = state.get("location_lon")
    radius_meters = int(state.get("location_radius_meters", 1500))
    limit = int(state.get("location_result_limit", 5))
    countrycodes = state.get("location_countrycodes")
    amenities = state.get("location_amenities") or []

    if lat is None or lon is None:
        if not query:
            raise ValueError("location_agent requires 'location_query'/'place_query' or 'location_lat'+'location_lon'.")
        geocode_results = _nominatim_search(query, limit=limit, countrycodes=countrycodes)
        if not geocode_results:
            raise ValueError(f"No map results found for query: {query}")
        primary = geocode_results[0]
        lat = float(primary["lat"])
        lon = float(primary["lon"])
    else:
        geocode_results = []

    log_task_update("Location Agent", f"Location pass #{call_number} started.", f"lat={lat}, lon={lon}")
    reverse_result = _nominatim_reverse(float(lat), float(lon))
    nearby = _overpass_nearby(float(lat), float(lon), radius_meters, amenities=amenities, limit=25)

    payload = {
        "query": query,
        "coordinates": {"lat": float(lat), "lon": float(lon)},
        "geocode_results": geocode_results,
        "reverse_result": reverse_result,
        "nearby_places": nearby,
        "map_links": {
            "openstreetmap": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}",
            "google_maps": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
        },
    }

    prompt = f"""
You are a location intelligence agent.

Objective:
{state.get("current_objective") or state.get("user_query", "")}

Analyze this place information and produce a meaningful summary.
Cover:
- where the place is
- what kind of locality it appears to be
- notable nearby facilities and amenity signals
- likely residential, commercial, transit, or institutional characteristics
- any practical observations useful for planning, research, or field understanding

Location payload:
{json.dumps(payload, indent=2, ensure_ascii=False)[:30000]}
""".strip()
    summary = llm_text(prompt)

    write_text_file(f"location_agent_{call_number}.txt", summary)
    write_text_file(f"location_agent_{call_number}.json", json.dumps(payload, indent=2, ensure_ascii=False))
    state["location_results"] = payload
    state["location_summary"] = summary
    state["draft_response"] = summary
    log_task_update("Location Agent", f"Location analysis saved to {OUTPUT_DIR}/location_agent_{call_number}.txt")
    return publish_agent_output(
        state,
        "location_agent",
        summary,
        f"location_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent", "reviewer_agent", "report_agent"],
    )
