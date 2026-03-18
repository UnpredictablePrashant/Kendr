import os
from urllib.parse import urlparse

from fastmcp import FastMCP

from mcp_servers.security_common import binary_exists, parse_nmap_xml, resolve_mcp_output, run_command


mcp = FastMCP("super-agent-nmap")


def _host_from_target(target: str) -> str:
    parsed = urlparse(target if target.startswith(("http://", "https://")) else f"https://{target}")
    return parsed.hostname or target


@mcp.tool
def service_scan(target: str, top_ports: int = 200, ports: str = "", timeout_seconds: int = 300) -> dict:
    if not binary_exists("nmap"):
        return {"available": False, "error": "nmap is not installed on PATH."}
    host = _host_from_target(target)
    xml_path = resolve_mcp_output(f"nmap_service_scan_{host.replace('.', '_')}.xml")
    cmd = ["nmap", "-Pn", "-sT", "-sV", "--version-light"]
    if ports.strip():
        cmd.extend(["-p", ports.strip()])
    else:
        cmd.extend(["--top-ports", str(top_ports)])
    cmd.extend(["-oX", xml_path, host])
    execution = run_command(cmd, timeout=timeout_seconds)
    return {
        "available": True,
        "target": target,
        "target_host": host,
        "xml_path": xml_path,
        "execution": execution,
        "parsed": parse_nmap_xml(xml_path),
    }


@mcp.tool
def host_discovery(target: str, timeout_seconds: int = 180) -> dict:
    if not binary_exists("nmap"):
        return {"available": False, "error": "nmap is not installed on PATH."}
    host = _host_from_target(target)
    cmd = ["nmap", "-sn", host]
    return {
        "available": True,
        "target": target,
        "target_host": host,
        "execution": run_command(cmd, timeout=timeout_seconds),
    }


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8003"))
    transport = os.getenv("MCP_TRANSPORT", "http")
    mcp.run(transport=transport, host=host, port=port)
