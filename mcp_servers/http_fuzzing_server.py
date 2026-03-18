import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastmcp import FastMCP


mcp = FastMCP("super-agent-http-surface")


def _request(url: str, method: str = "GET", timeout: int = 15) -> dict:
    request = Request(url, method=method, headers={"User-Agent": os.getenv("RESEARCH_USER_AGENT", "multi-agent-http-probe/1.0")})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return {
                "url": url,
                "method": method,
                "status": getattr(response, "status", None),
                "headers": dict(response.headers.items()),
                "body_excerpt": body[:4000],
                "error": "",
            }
    except HTTPError as exc:
        return {
            "url": url,
            "method": method,
            "status": exc.code,
            "headers": dict(exc.headers.items()),
            "body_excerpt": exc.read().decode("utf-8", errors="ignore")[:4000],
            "error": str(exc),
        }
    except URLError as exc:
        return {"url": url, "method": method, "status": None, "headers": {}, "body_excerpt": "", "error": str(exc)}
    except Exception as exc:
        return {"url": url, "method": method, "status": None, "headers": {}, "body_excerpt": "", "error": str(exc)}


@mcp.tool
def probe_common_paths(base_url: str, paths_csv: str = "/robots.txt,/sitemap.xml,/.well-known/security.txt,/openapi.json,/swagger.json") -> dict:
    items = []
    for raw_path in [item.strip() for item in paths_csv.split(",") if item.strip()]:
        if raw_path.startswith("http://") or raw_path.startswith("https://"):
            url = raw_path
        else:
            url = base_url.rstrip("/") + raw_path
        items.append(_request(url))
    return {"base_url": base_url, "results": items}


@mcp.tool
def method_matrix(url: str, methods_csv: str = "GET,HEAD,OPTIONS") -> dict:
    methods = [item.strip().upper() for item in methods_csv.split(",") if item.strip()]
    return {"url": url, "results": [_request(url, method=method) for method in methods]}


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8006"))
    transport = os.getenv("MCP_TRANSPORT", "http")
    mcp.run(transport=transport, host=host, port=port)
