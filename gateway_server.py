from __future__ import annotations

import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from superagent import AgentRuntime, build_registry
from tasks.sqlite_store import (
    list_channel_sessions,
    list_heartbeat_events,
    list_monitor_events,
    list_monitor_rules,
    list_recent_runs,
    list_scheduled_jobs,
)


REGISTRY = build_registry()
RUNTIME = AgentRuntime(REGISTRY)


def _html_page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; line-height: 1.5; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; }}
    code, pre {{ background: #f5f5f5; border-radius: 6px; padding: 4px 6px; }}
    pre {{ white-space: pre-wrap; }}
  </style>
</head>
<body>
{body}
</body>
</html>""".encode("utf-8")


class GatewayHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict | list):
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status: int, title: str, body: str):
        page = _html_page(title, body)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._handle_home()
            return
        if parsed.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if parsed.path == "/registry/agents":
            self._send_json(
                200,
                [
                    {
                        "name": agent.name,
                        "description": agent.description,
                        "plugin": agent.plugin_name,
                        "skills": agent.skills,
                    }
                    for agent in REGISTRY.agents.values()
                ],
            )
            return
        if parsed.path == "/registry/plugins":
            self._send_json(
                200,
                [
                    {
                        "name": plugin.name,
                        "source": plugin.source,
                        "description": plugin.description,
                        "version": plugin.version,
                        "kind": plugin.kind,
                    }
                    for plugin in REGISTRY.plugins.values()
                ],
            )
            return
        if parsed.path == "/runs":
            self._send_json(200, list_recent_runs())
            return
        if parsed.path == "/sessions":
            self._send_json(200, list_channel_sessions())
            return
        if parsed.path == "/jobs":
            self._send_json(200, list_scheduled_jobs())
            return
        if parsed.path == "/monitors":
            self._send_json(200, list_monitor_rules())
            return
        if parsed.path == "/monitor-events":
            self._send_json(200, list_monitor_events())
            return
        if parsed.path == "/heartbeats":
            self._send_json(200, list_heartbeat_events())
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/ingest":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                raise ValueError("JSON body must be an object.")
        except Exception as exc:
            self._send_json(400, {"error": "invalid_json", "detail": str(exc)})
            return

        text = str(payload.get("text") or payload.get("message") or payload.get("user_query") or "").strip()
        if not text:
            self._send_json(400, {"error": "missing_text", "detail": "Provide text, message, or user_query."})
            return

        state_overrides = {
            "max_steps": int(payload.get("max_steps", 20)),
            "incoming_channel": payload.get("channel", "webchat"),
            "incoming_sender_id": payload.get("sender_id", ""),
            "incoming_chat_id": payload.get("chat_id", ""),
            "incoming_workspace_id": payload.get("workspace_id", ""),
            "incoming_text": text,
            "incoming_is_group": bool(payload.get("is_group", False)),
            "incoming_mentions_assistant": bool(payload.get("mentions_assistant", False)),
            "incoming_payload": payload,
        }
        try:
            result = RUNTIME.run_query(text, state_overrides=state_overrides)
            self._send_json(
                200,
                {
                    "run_id": result.get("run_id"),
                    "output_dir": result.get("run_output_dir", ""),
                    "final_output": result.get("final_output") or result.get("draft_response", ""),
                    "last_agent": result.get("last_agent", ""),
                },
            )
        except Exception as exc:
            self._send_json(500, {"error": "workflow_failed", "detail": str(exc)})

    def _handle_home(self):
        agents = list(REGISTRY.agents.values())
        plugins = list(REGISTRY.plugins.values())
        runs = list_recent_runs(8)
        sessions = list_channel_sessions(8)
        jobs = list_scheduled_jobs(8)
        monitors = list_monitor_rules(8)
        heartbeats = list_heartbeat_events(8)
        body = f"""
        <h1>Superagent Gateway</h1>
        <p>Plugin-driven agent runtime with dynamic discovery, CLI control, and HTTP ingress.</p>
        <div class="grid">
          <div class="card">
            <h2>Registry</h2>
            <p>Agents: <strong>{len(agents)}</strong></p>
            <p>Plugins: <strong>{len(plugins)}</strong></p>
            <p><a href="/registry/agents">/registry/agents</a></p>
            <p><a href="/registry/plugins">/registry/plugins</a></p>
          </div>
          <div class="card">
            <h2>Gateway</h2>
            <p>POST channel payloads to <code>/ingest</code>.</p>
<pre>{html.escape(json.dumps({"channel": "webchat", "sender_id": "u1", "chat_id": "c1", "text": "hello"}, indent=2))}</pre>
          </div>
          <div class="card">
            <h2>Activity</h2>
            <p><a href="/runs">/runs</a></p>
            <p><a href="/sessions">/sessions</a></p>
            <p><a href="/jobs">/jobs</a></p>
            <p><a href="/monitors">/monitors</a></p>
            <p><a href="/monitor-events">/monitor-events</a></p>
            <p><a href="/heartbeats">/heartbeats</a></p>
          </div>
        </div>
        <div class="grid">
          <div class="card">
            <h2>Recent Runs</h2>
            <pre>{html.escape(json.dumps(runs, indent=2, ensure_ascii=False))}</pre>
          </div>
          <div class="card">
            <h2>Recent Sessions</h2>
            <pre>{html.escape(json.dumps(sessions, indent=2, ensure_ascii=False))}</pre>
          </div>
          <div class="card">
            <h2>Scheduled Jobs</h2>
            <pre>{html.escape(json.dumps(jobs, indent=2, ensure_ascii=False))}</pre>
          </div>
          <div class="card">
            <h2>Monitor Rules</h2>
            <pre>{html.escape(json.dumps(monitors, indent=2, ensure_ascii=False))}</pre>
          </div>
          <div class="card">
            <h2>Heartbeats</h2>
            <pre>{html.escape(json.dumps(heartbeats, indent=2, ensure_ascii=False))}</pre>
          </div>
        </div>
        """
        self._send_html(200, "Superagent Gateway", body)


def main() -> None:
    host = os.getenv("GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("GATEWAY_PORT", "8790"))
    server = ThreadingHTTPServer((host, port), GatewayHandler)
    print(f"Gateway server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
