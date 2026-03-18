import json
import os
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def run_command(cmd: list[str], timeout: int = 300) -> dict:
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-30000:],
            "stderr": completed.stderr[-12000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "returncode": None,
            "stdout": (exc.stdout or "")[-30000:] if exc.stdout else "",
            "stderr": (exc.stderr or "")[-12000:] if exc.stderr else "",
            "timed_out": True,
            "error": f"Command timed out after {timeout} seconds.",
        }
    except Exception as exc:
        return {
            "command": cmd,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "error": str(exc),
        }


def resolve_mcp_output(filename: str) -> str:
    base = Path(os.getenv("MCP_OUTPUT_DIR", "output/mcp"))
    base.mkdir(parents=True, exist_ok=True)
    return str(base / filename)


def parse_nmap_xml(path: str) -> dict:
    xml_path = Path(path)
    if not xml_path.exists():
        return {"hosts": [], "summary": "No Nmap XML file found."}
    try:
        root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"hosts": [], "summary": f"Unable to parse Nmap XML: {exc}"}

    hosts = []
    for host in root.findall("host"):
        addresses = [item.get("addr", "") for item in host.findall("address") if item.get("addr")]
        ports = []
        for port in host.findall("./ports/port"):
            service = port.find("service")
            state_el = port.find("state")
            ports.append(
                {
                    "protocol": port.get("protocol", ""),
                    "port": port.get("portid", ""),
                    "state": state_el.get("state", "") if state_el is not None else "",
                    "service": service.get("name", "") if service is not None else "",
                    "product": service.get("product", "") if service is not None else "",
                    "version": service.get("version", "") if service is not None else "",
                }
            )
        hosts.append({"addresses": addresses, "ports": ports})
    return {"hosts": hosts, "summary": f"Parsed {len(hosts)} host entries."}


def capture_page(url: str, filename: str | None = None, *, headless: bool = True, actions: list[dict] | None = None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"available": False, "error": f"Playwright is unavailable: {exc}"}

    screenshot_name = filename or f"screenshot_{uuid.uuid4().hex}.png"
    screenshot_path = resolve_mcp_output(screenshot_name)
    actions = actions or []
    execution_log = []
    extracted_items = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=45000)
            execution_log.append({"action": "goto", "url": url, "status": "ok"})
            for step in actions:
                if not isinstance(step, dict):
                    continue
                action = str(step.get("action", "")).strip().lower()
                selector = str(step.get("selector", "")).strip()
                try:
                    if action == "click":
                        page.click(selector, timeout=15000)
                    elif action == "fill":
                        page.fill(selector, str(step.get("value", "")), timeout=15000)
                    elif action == "press":
                        page.press(selector, str(step.get("key", "Enter")), timeout=15000)
                    elif action == "wait_for_selector":
                        page.wait_for_selector(selector, timeout=15000)
                    elif action == "extract_text":
                        extracted_items.append({"selector": selector, "text": page.locator(selector).inner_text(timeout=15000)[:5000]})
                    execution_log.append({"action": action, "selector": selector, "status": "ok"})
                except Exception as exc:
                    execution_log.append({"action": action, "selector": selector, "status": "error", "detail": str(exc)})
            page.screenshot(path=screenshot_path, full_page=True)
            payload = {
                "available": True,
                "screenshot_path": screenshot_path,
                "title": page.title(),
                "final_url": page.url,
                "text_excerpt": page.locator("body").inner_text(timeout=15000)[:5000],
                "execution_log": execution_log,
                "extracted_items": extracted_items,
            }
            browser.close()
            return payload
    except Exception as exc:
        return {"available": True, "error": str(exc), "screenshot_path": screenshot_path, "execution_log": execution_log}


def http_json(url: str, *, params: dict | None = None, method: str = "GET", body: dict | None = None, timeout: int = 30, headers: dict | None = None) -> dict:
    final_url = url
    if params:
        final_url += ("&" if "?" in url else "?") + urlencode(params)
    data = None
    request_headers = {"User-Agent": os.getenv("RESEARCH_USER_AGENT", "multi-agent-mcp/1.0")}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(final_url, data=data, method=method, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
        return {
            "status": getattr(response, "status", None),
            "url": final_url,
            "headers": dict(response.headers.items()),
            "json": json.loads(raw) if raw.strip() else {},
            "raw": raw[:50000],
        }


def binary_exists(name: str) -> bool:
    return shutil.which(name) is not None
