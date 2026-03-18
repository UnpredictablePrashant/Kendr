import os

from fastmcp import FastMCP

from mcp_servers.security_common import http_json


mcp = FastMCP("super-agent-cve")


def _nvd_headers() -> dict:
    api_key = os.getenv("NVD_API_KEY", "").strip()
    return {"apiKey": api_key} if api_key else {}


@mcp.tool
def lookup_cve(cve_id: str) -> dict:
    return http_json(
        os.getenv("CVE_API_BASE_URL", "https://services.nvd.nist.gov/rest/json/cves/2.0"),
        params={"cveId": cve_id},
        headers=_nvd_headers(),
        timeout=30,
    )


@mcp.tool
def search_cves(keyword: str, limit: int = 10) -> dict:
    payload = http_json(
        os.getenv("CVE_API_BASE_URL", "https://services.nvd.nist.gov/rest/json/cves/2.0"),
        params={"keywordSearch": keyword, "resultsPerPage": str(limit)},
        headers=_nvd_headers(),
        timeout=30,
    )
    payload["keyword"] = keyword
    payload["limit"] = limit
    return payload


@mcp.tool
def osv_package_query(ecosystem: str, package_name: str, version: str = "") -> dict:
    body = {"package": {"ecosystem": ecosystem, "name": package_name}}
    if version:
        body["version"] = version
    return http_json("https://api.osv.dev/v1/query", method="POST", body=body, timeout=30)


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8007"))
    transport = os.getenv("MCP_TRANSPORT", "http")
    mcp.run(transport=transport, host=host, port=port)
