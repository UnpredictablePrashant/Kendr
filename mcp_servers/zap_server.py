import json
import os
from pathlib import Path

from fastmcp import FastMCP

from mcp_servers.security_common import binary_exists, resolve_mcp_output, run_command


mcp = FastMCP("super-agent-zap")


@mcp.tool
def baseline_scan(url: str, max_minutes: int = 3, timeout_seconds: int = 600) -> dict:
    if not binary_exists("zap-baseline.py"):
        return {"available": False, "error": "zap-baseline.py is not installed on PATH."}
    json_path = resolve_mcp_output("zap_baseline_report.json")
    html_path = resolve_mcp_output("zap_baseline_report.html")
    cmd = ["zap-baseline.py", "-t", url, "-m", str(max_minutes), "-J", json_path, "-r", html_path]
    execution = run_command(cmd, timeout=timeout_seconds)
    parsed = {}
    if Path(json_path).exists():
        try:
            parsed = json.loads(Path(json_path).read_text(encoding="utf-8", errors="ignore"))
        except Exception as exc:
            parsed = {"parse_error": str(exc)}
    return {
        "available": True,
        "url": url,
        "json_path": json_path,
        "html_path": html_path,
        "execution": execution,
        "parsed": parsed,
    }


@mcp.tool
def version_info() -> dict:
    if not binary_exists("zap-baseline.py"):
        return {"available": False, "error": "zap-baseline.py is not installed on PATH."}
    return {"available": True, "execution": run_command(["zap-baseline.py", "-h"], timeout=60)}


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8004"))
    transport = os.getenv("MCP_TRANSPORT", "http")
    mcp.run(transport=transport, host=host, port=port)
