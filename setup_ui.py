from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from tasks.setup_registry import (
    build_google_oauth_start_url,
    build_microsoft_oauth_start_url,
    build_setup_snapshot,
    build_slack_oauth_start_url,
    exchange_google_oauth_code,
    exchange_microsoft_oauth_code,
    exchange_slack_oauth_code,
    issue_oauth_state_token,
)


PENDING_STATES: dict[str, str] = {}


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.5; }}
    h1 {{ margin-bottom: 8px; }}
    .card {{ border: 1px solid #ddd; padding: 16px; border-radius: 8px; margin-bottom: 16px; }}
    .ok {{ color: #0a7b34; }}
    .bad {{ color: #b42318; }}
    code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 4px; }}
    a.button {{ display: inline-block; padding: 8px 12px; border-radius: 6px; background: #0b57d0; color: #fff; text-decoration: none; }}
    ul {{ padding-left: 18px; }}
  </style>
</head>
<body>
{body}
</body>
</html>""".encode("utf-8")


class SetupHandler(BaseHTTPRequestHandler):
    def _send_html(self, status: int, title: str, body: str) -> None:
        page = _page(title, body)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._handle_home()
            return
        if parsed.path == "/oauth/google/start":
            self._handle_oauth_start("google")
            return
        if parsed.path == "/oauth/microsoft/start":
            self._handle_oauth_start("microsoft")
            return
        if parsed.path == "/oauth/slack/start":
            self._handle_oauth_start("slack")
            return
        if parsed.path == "/oauth/google/callback":
            self._handle_oauth_callback("google", parse_qs(parsed.query))
            return
        if parsed.path == "/oauth/microsoft/callback":
            self._handle_oauth_callback("microsoft", parse_qs(parsed.query))
            return
        if parsed.path == "/oauth/slack/callback":
            self._handle_oauth_callback("slack", parse_qs(parsed.query))
            return
        self._send_html(404, "Not Found", "<h1>Not Found</h1>")

    def _handle_home(self) -> None:
        snapshot = build_setup_snapshot([])
        services = snapshot["services"]
        actions = []
        for key in ("google_workspace", "microsoft_graph", "slack"):
            item = services.get(key, {})
            if item.get("oauth_ready") and not item.get("configured") and item.get("setup_url"):
                actions.append(f'<li><a class="button" href="{html.escape(item["setup_url"])}">Connect {html.escape(key)}</a></li>')

        service_rows = []
        for service_name, item in services.items():
            klass = "ok" if item["configured"] else "bad"
            label = "configured" if item["configured"] else "not configured"
            oauth = " | OAuth ready" if item.get("oauth_ready") and not item["configured"] else ""
            service_rows.append(
                f'<li><strong>{html.escape(service_name)}</strong>: <span class="{klass}">{label}</span>{html.escape(oauth)}'
                f'<br>{html.escape(item.get("details", ""))}</li>'
            )

        body = f"""
        <h1>Integration Setup</h1>
        <p>This local UI shows what the agent ecosystem can actually use on this machine right now.</p>
        <div class="card">
          <h2>Services</h2>
          <ul>{''.join(service_rows)}</ul>
        </div>
        <div class="card">
          <h2>OAuth Actions</h2>
          <ul>{''.join(actions) if actions else '<li>No OAuth actions available right now.</li>'}</ul>
        </div>
        <div class="card">
          <h2>Output Files</h2>
          <p>Status is also written to <code>output/setup_status.json</code> and <code>output/setup_status.txt</code>.</p>
        </div>
        """
        self._send_html(200, "Integration Setup", body)

    def _handle_oauth_start(self, provider: str) -> None:
        state_token = issue_oauth_state_token()
        PENDING_STATES[state_token] = provider
        if provider == "google":
            url = build_google_oauth_start_url(state_token)
        elif provider == "microsoft":
            url = build_microsoft_oauth_start_url(state_token)
        else:
            url = build_slack_oauth_start_url(state_token)
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def _handle_oauth_callback(self, provider: str, query: dict) -> None:
        state_token = (query.get("state") or [""])[0]
        code = (query.get("code") or [""])[0]
        error = (query.get("error") or [""])[0]
        if error:
            self._send_html(400, "OAuth Error", f"<h1>OAuth failed</h1><p>{html.escape(error)}</p>")
            return
        if not code:
            self._send_html(400, "OAuth Error", "<h1>OAuth failed</h1><p>Missing authorization code.</p>")
            return
        if PENDING_STATES.get(state_token) != provider:
            self._send_html(400, "OAuth Error", "<h1>OAuth failed</h1><p>Invalid or expired state token.</p>")
            return
        try:
            if provider == "google":
                exchange_google_oauth_code(code)
            elif provider == "microsoft":
                exchange_microsoft_oauth_code(code)
            else:
                exchange_slack_oauth_code(code)
            PENDING_STATES.pop(state_token, None)
            build_setup_snapshot([])
            self._send_html(
                200,
                "OAuth Complete",
                (
                    f"<h1>{html.escape(provider.title())} connected</h1>"
                    "<p>The token has been stored in <code>output/integration_tokens.json</code>.</p>"
                    '<p><a class="button" href="/">Return to setup home</a></p>'
                ),
            )
        except Exception as exc:
            self._send_html(500, "OAuth Error", f"<h1>OAuth failed</h1><p>{html.escape(str(exc))}</p>")


def main() -> None:
    host = os.getenv("SETUP_UI_HOST", "127.0.0.1")
    port = int(os.getenv("SETUP_UI_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), SetupHandler)
    print(f"Setup UI running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
