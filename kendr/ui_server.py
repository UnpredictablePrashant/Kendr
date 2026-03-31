from __future__ import annotations

import html as _html
import json
import logging
import os
import queue
import threading
import time
import traceback

import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

_log = logging.getLogger("kendr.ui")

from tasks.setup_config_store import (
    apply_setup_env_defaults,
    export_env_lines,
    get_setup_component_snapshot,
    save_component_values,
    set_component_enabled,
    setup_overview,
)

try:
    from kendr.persistence import (
        list_agent_executions_for_run as _list_run_steps,
        list_artifacts_for_run as _list_run_artifacts,
        get_run as _db_get_run,
    )
    _HAS_PERSISTENCE = True
except Exception:
    _HAS_PERSISTENCE = False
    def _list_run_steps(run_id):  # type: ignore[misc]
        return []
    def _list_run_artifacts(run_id):  # type: ignore[misc]
        return []
    def _db_get_run(run_id):  # type: ignore[misc]
        return None

try:
    from kendr.providers import (
        build_google_oauth_config,
        build_google_oauth_start_url,
        build_microsoft_oauth_config,
        build_microsoft_oauth_start_url,
        build_slack_oauth_config,
        build_slack_oauth_start_url,
        exchange_google_oauth_code,
        exchange_microsoft_oauth_code,
        exchange_slack_oauth_code,
    )
    from kendr.setup import issue_oauth_state_token
    _HAS_OAUTH = True
except Exception:
    _HAS_OAUTH = False

try:
    from kendr.setup.catalog import INTEGRATION_DEFINITIONS as _INTEGRATION_DEFS
    _OAUTH_PATH_MAP: dict[str, str] = {
        d.id: d.oauth_start_path
        for d in _INTEGRATION_DEFS
        if getattr(d, "oauth_start_path", "")
    }
except Exception:
    _OAUTH_PATH_MAP = {}

_UI_PORT = int(os.getenv("KENDR_UI_PORT", "2151"))
_UI_HOST = os.getenv("KENDR_UI_HOST", "127.0.0.1")

try:
    from kendr.mcp_manager import (
        list_servers as _mcp_list_servers,
        get_server as _mcp_get_server,
        add_server as _mcp_add_server,
        remove_server as _mcp_remove_server,
        toggle_server as _mcp_toggle_server,
        discover_tools as _mcp_discover_tools,
        SCAFFOLD_CODE as _MCP_SCAFFOLD_CODE,
    )
    _HAS_MCP_MANAGER = True
except Exception as _mcp_import_exc:
    _HAS_MCP_MANAGER = False
    _log.warning("MCP manager not available: %s", _mcp_import_exc)

_GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
_GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8790"))


def _gateway_url() -> str:
    return f"http://{_GATEWAY_HOST}:{_GATEWAY_PORT}"


def _gateway_ready(timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(f"{_gateway_url()}/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _gateway_ingest(payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{_gateway_url()}/ingest",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=360) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _gateway_get(path: str, timeout: float = 5.0) -> dict | list:
    req = urllib.request.Request(f"{_gateway_url()}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


_pending_runs: dict[str, dict] = {}
_run_event_queues: dict[str, "queue.Queue[dict]"] = {}
_pending_lock = threading.Lock()
_OAUTH_PENDING_STATES: dict[str, str] = {}


def _push_event(run_id: str, event_type: str, data: dict) -> None:
    with _pending_lock:
        q = _run_event_queues.get(run_id)
    if q is not None:
        q.put({"type": event_type, "data": data})


def _format_step(step: dict) -> dict:
    excerpt = str(step.get("output_excerpt") or "").strip()
    agent = step.get("agent_name", "agent")
    return {
        "agent": agent,
        "status": step.get("status", "running"),
        "message": excerpt or f"Running {agent}...",
        "execution_id": step.get("execution_id"),
    }


def _collect_artifacts(run_id: str, output_dir: str) -> tuple[list[dict], list[dict]]:
    db_artifacts: list[dict] = []
    file_list: list[dict] = []
    try:
        db_artifacts = _list_run_artifacts(run_id)
    except Exception:
        pass
    try:
        if output_dir and os.path.isdir(output_dir):
            for fname in sorted(os.listdir(output_dir))[:50]:
                fp = os.path.join(output_dir, fname)
                if os.path.isfile(fp):
                    file_list.append({
                        "name": fname,
                        "path": fp,
                        "size": os.path.getsize(fp),
                    })
    except Exception:
        pass
    return db_artifacts, file_list


def _start_run_background(run_id: str, payload: dict) -> None:
    def _poll_db_steps() -> None:
        seen: set = set()
        while True:
            with _pending_lock:
                current = _pending_runs.get(run_id, {})
            done = current.get("status") in ("completed", "failed")
            try:
                for step in _list_run_steps(run_id):
                    eid = step.get("execution_id")
                    if eid and eid not in seen:
                        seen.add(eid)
                        _push_event(run_id, "step", _format_step(step))
            except Exception as _step_exc:
                _log.debug("Step poll error for run %s: %s", run_id, _step_exc)
            if done:
                break
            time.sleep(0.6)

    def _run() -> None:
        _push_event(run_id, "status", {"status": "running", "message": "Agents mobilizing..."})
        poll = threading.Thread(target=_poll_db_steps, daemon=True)
        poll.start()
        try:
            result = _gateway_ingest(payload)
            db_artifacts, file_list = _collect_artifacts(run_id, result.get("output_dir", ""))
            result["artifacts"] = db_artifacts
            result["artifact_files"] = file_list
            with _pending_lock:
                _pending_runs[run_id] = {"status": "completed", "result": result}
            _push_event(run_id, "result", result)
            _push_event(run_id, "done", {"run_id": run_id, "status": "completed"})
        except urllib.error.URLError as exc:
            err = str(exc)
            with _pending_lock:
                _pending_runs[run_id] = {"status": "failed", "error": err}
            _push_event(run_id, "error", {"message": err})
            _push_event(run_id, "done", {"run_id": run_id, "status": "failed"})
        except Exception as exc:
            err = traceback.format_exc()
            with _pending_lock:
                _pending_runs[run_id] = {"status": "failed", "error": err}
            _push_event(run_id, "error", {"message": str(exc)})
            _push_event(run_id, "done", {"run_id": run_id, "status": "failed"})

    t = threading.Thread(target=_run, daemon=True)
    t.start()


_CHAT_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kendr — Chat</title>
<style>
:root {
  --teal: #00C9A7; --amber: #FFB347; --crimson: #FF4757; --blue: #5352ED;
  --bg: #0d0f14; --surface: #161b22; --surface2: #1e2530; --border: #2a3140;
  --text: #e6edf3; --muted: #7d8590; --sidebar-w: 280px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); height: 100vh; display: flex; overflow: hidden; }
a { color: var(--teal); text-decoration: none; }
a:hover { text-decoration: underline; }
.sidebar { width: var(--sidebar-w); min-width: var(--sidebar-w); background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.sidebar-header { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
.logo { font-size: 22px; font-weight: 800; color: var(--teal); letter-spacing: 0.05em; }
.logo span { color: var(--amber); }
.tagline { font-size: 11px; color: var(--muted); margin-top: 4px; }
.sidebar-nav { padding: 12px 8px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.nav-btn { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; border: none; background: transparent; width: 100%; text-align: left; text-decoration: none; transition: background 0.15s, color 0.15s; }
.nav-btn:hover { background: var(--surface2); color: var(--text); }
.nav-btn.active { background: rgba(0, 201, 167, 0.12); color: var(--teal); }
.nav-btn .icon { font-size: 16px; width: 20px; text-align: center; }
.sidebar-section { padding: 10px 16px 6px; font-size: 10px; font-weight: 700; color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase; }
.run-list { overflow-y: auto; flex: 1; padding: 0 8px 16px; }
.run-item { padding: 10px 12px; border-radius: 8px; cursor: pointer; margin-bottom: 2px; border: 1px solid transparent; transition: background 0.15s; }
.run-item:hover { background: var(--surface2); }
.run-item.active { background: rgba(83, 82, 237, 0.12); border-color: rgba(83, 82, 237, 0.3); }
.run-item-title { font-size: 12px; font-weight: 500; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.run-item-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
.run-badge { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; }
.run-badge.completed { background: rgba(0,201,167,0.15); color: var(--teal); }
.run-badge.failed { background: rgba(255,71,87,0.15); color: var(--crimson); }
.run-badge.running { background: rgba(255,179,71,0.15); color: var(--amber); }
.new-chat-btn { display: flex; align-items: center; justify-content: center; gap: 8px; margin: 12px 8px 4px; padding: 10px; background: rgba(0,201,167,0.1); border: 1px solid rgba(0,201,167,0.3); color: var(--teal); border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.15s; }
.new-chat-btn:hover { background: rgba(0,201,167,0.2); }
.chat-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: var(--bg); }
.chat-header { padding: 16px 24px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; background: var(--surface); }
.chat-title { font-size: 15px; font-weight: 600; color: var(--text); }
.chat-subtitle { font-size: 12px; color: var(--muted); }
.header-status { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--crimson); }
.status-dot.online { background: var(--teal); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }
.messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; scroll-behavior: smooth; }
.message-row { display: flex; gap: 12px; max-width: 900px; }
.message-row.user { flex-direction: row-reverse; margin-left: auto; }
.message-row.user .bubble { background: rgba(83,82,237,0.2); border-color: rgba(83,82,237,0.4); border-radius: 18px 4px 18px 18px; }
.avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; }
.avatar.kendr { background: rgba(0,201,167,0.15); border: 1px solid rgba(0,201,167,0.3); }
.avatar.user { background: rgba(83,82,237,0.2); border: 1px solid rgba(83,82,237,0.3); }
.bubble { padding: 14px 18px; border-radius: 4px 18px 18px 18px; border: 1px solid var(--border); background: var(--surface); max-width: 680px; font-size: 14px; line-height: 1.65; }
.bubble-meta { font-size: 11px; color: var(--muted); margin-top: 8px; }
.bubble pre { background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 8px; padding: 12px; overflow-x: auto; font-size: 13px; margin: 8px 0; white-space: pre-wrap; }
.steps-wrapper { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.step-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 10px; padding: 8px 12px; font-size: 12px; display: flex; align-items: center; gap: 8px; }
.step-card.running { border-color: rgba(255,179,71,0.4); }
.step-card.done { border-color: rgba(0,201,167,0.3); }
.step-card.failed { border-color: rgba(255,71,87,0.4); }
.step-icon { font-size: 14px; flex-shrink: 0; }
.step-info { flex: 1; }
.step-name { font-weight: 600; color: var(--text); }
.step-desc { color: var(--muted); font-size: 11px; margin-top: 2px; }
.typing-indicator { display: flex; align-items: center; gap: 4px; padding: 4px 0 8px; }
.typing-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: typing 1.4s infinite; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%,100% { transform: translateY(0); opacity: 0.5; } 50% { transform: translateY(-4px); opacity: 1; } }
.welcome { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 20px; padding: 40px; text-align: center; }
.welcome-logo { font-size: 56px; color: var(--teal); filter: drop-shadow(0 0 20px rgba(0,201,167,0.4)); }
.welcome h2 { font-size: 24px; font-weight: 700; color: var(--text); }
.welcome p { font-size: 14px; color: var(--muted); max-width: 480px; line-height: 1.7; }
.suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 8px; }
.suggest-chip { padding: 8px 16px; border: 1px solid var(--border); border-radius: 20px; font-size: 13px; color: var(--muted); cursor: pointer; transition: all 0.15s; background: var(--surface); }
.suggest-chip:hover { border-color: var(--teal); color: var(--teal); background: rgba(0,201,167,0.06); }
.input-area { padding: 16px 24px 20px; border-top: 1px solid var(--border); background: var(--surface); }
.input-row { display: flex; gap: 12px; align-items: flex-end; }
.input-box { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 14px; padding: 14px 18px; color: var(--text); font-size: 14px; font-family: inherit; resize: none; min-height: 52px; max-height: 200px; overflow-y: auto; line-height: 1.5; transition: border-color 0.15s; outline: none; }
.input-box:focus { border-color: var(--teal); }
.input-box::placeholder { color: var(--muted); }
.send-btn { width: 48px; height: 48px; border-radius: 12px; background: var(--teal); border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0; transition: background 0.15s, opacity 0.15s; color: #0d0f14; }
.send-btn:hover { background: #00b396; }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.input-hint { font-size: 11px; color: var(--muted); margin-top: 8px; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
.error-banner { background: rgba(255,71,87,0.1); border: 1px solid rgba(255,71,87,0.3); color: var(--crimson); border-radius: 8px; padding: 10px 14px; font-size: 13px; display: flex; gap: 8px; align-items: flex-start; }
.streaming-status { font-size: 11px; color: var(--amber); margin-top: 4px; font-style: italic; }
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-header">
    <div class="logo">kendr<span>.</span></div>
    <div class="tagline">Multi-agent intelligence runtime</div>
  </div>
  <div class="sidebar-nav">
    <a href="/" class="nav-btn active"><span class="icon">💬</span> Chat</a>
    <a href="/setup" class="nav-btn"><span class="icon">⚙️</span> Setup & Config</a>
    <a href="/runs" class="nav-btn"><span class="icon">📋</span> Run History</a>
    <a href="/mcp" class="nav-btn"><span class="icon">🧩</span> MCP Servers</a>
  </div>
  <button class="new-chat-btn" onclick="newChat()">+ New Chat</button>
  <div class="sidebar-section">Recent Runs</div>
  <div class="run-list" id="runList"></div>
</div>
<div class="chat-main">
  <div class="chat-header">
    <div>
      <div class="chat-title" id="chatTitle">New Chat</div>
      <div class="chat-subtitle">Powered by kendr multi-agent runtime</div>
    </div>
    <div class="header-status">
      <div class="status-dot" id="gatewayDot"></div>
      <span id="gatewayStatus">Checking gateway...</span>
    </div>
  </div>
  <div class="messages" id="messages">
    <div class="welcome" id="welcome">
      <div class="welcome-logo">&#x26A1;</div>
      <h2>What would you like to research or build?</h2>
      <p>Kendr orchestrates specialized AI agents to research, generate code, deploy applications, analyze data, and automate complex workflows &#x2014; all from a single query.</p>
      <div class="suggestions">
        <div class="suggest-chip" onclick="fillInput('Create a competitive intelligence brief on Stripe')">&#x1F4CA; Stripe competitive brief</div>
        <div class="suggest-chip" onclick="fillInput('Build a FastAPI REST API with JWT authentication and PostgreSQL')">&#x1F3D7;&#xFE0F; FastAPI + JWT + PostgreSQL</div>
        <div class="suggest-chip" onclick="fillInput('Write API tests for https://jsonplaceholder.typicode.com')">&#x1F9EA; API test generation</div>
        <div class="suggest-chip" onclick="fillInput('Summarize my unread emails and Slack messages from today')">&#x1F4EC; Communications digest</div>
        <div class="suggest-chip" onclick="fillInput('Dockerize a Node.js app and write a docker-compose.yml')">&#x1F433; Dockerize + compose</div>
        <div class="suggest-chip" onclick="fillInput('Deploy a React app to AWS S3 and CloudFront')">&#x2601;&#xFE0F; Deploy to AWS</div>
      </div>
    </div>
  </div>
  <div class="input-area">
    <div class="input-row">
      <textarea class="input-box" id="userInput" placeholder="Ask kendr anything &#x2014; research, code, deploy, analyze..." rows="1" onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
      <button class="send-btn" id="sendBtn" onclick="sendMessage()" title="Send (Enter)">&#x27A4;</button>
    </div>
    <div class="input-hint">Enter to send &#xB7; Shift+Enter for new line &#xB7; Gateway auto-starts if not running</div>
  </div>
</div>
<script>
const API = '';
let currentRunId = null;
let isRunning = false;
let gatewayOnline = false;
let workingDir = '';
let activeEvtSource = null;

async function checkGateway() {
  try {
    const r = await fetch(API + '/api/gateway/status');
    const d = await r.json();
    gatewayOnline = d.online;
    workingDir = d.working_dir || '';
    const dot = document.getElementById('gatewayDot');
    const status = document.getElementById('gatewayStatus');
    if (gatewayOnline) {
      dot.classList.add('online');
      status.textContent = 'Gateway online';
    } else {
      dot.classList.remove('online');
      status.textContent = 'Gateway offline \u2014 run: kendr gateway start';
    }
  } catch(e) {
    document.getElementById('gatewayDot').classList.remove('online');
    document.getElementById('gatewayStatus').textContent = 'UI server error';
  }
}

async function loadRuns() {
  try {
    const r = await fetch(API + '/api/runs');
    if (!r.ok) return;
    const runs = await r.json();
    const list = document.getElementById('runList');
    list.innerHTML = '';
    (runs || []).slice(0, 20).forEach(run => {
      const div = document.createElement('div');
      div.className = 'run-item' + (run.run_id === currentRunId ? ' active' : '');
      const text = (run.query || run.text || 'Run').substring(0, 50);
      const ts = run.created_at ? new Date(run.created_at).toLocaleTimeString() : '';
      const status = (run.status || 'completed').toLowerCase();
      div.innerHTML = '<div class="run-item-title">' + esc(text) + '</div>' +
        '<div class="run-item-meta"><span class="run-badge ' + status + '">' + status + '</span>' + (ts ? ' \xB7 ' + ts : '') + '</div>';
      div.onclick = () => loadRun(run.run_id);
      list.appendChild(div);
    });
  } catch(e) {}
}

async function loadRun(runId) {
  try {
    const r = await fetch(API + '/api/runs/' + runId);
    const d = await r.json();
    const output = d.final_output || d.output || '';
    const query = d.query || d.text || '';
    if (query) { clearMessages(); appendUserMsg(query); if (output) appendKendrMsg(output, runId); }
  } catch(e) {}
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function newChat() {
  currentRunId = null;
  if (activeEvtSource) { activeEvtSource.close(); activeEvtSource = null; }
  clearMessages();
  document.getElementById('chatTitle').textContent = 'New Chat';
  document.getElementById('userInput').focus();
}

function clearMessages() {
  const msgs = document.getElementById('messages');
  msgs.innerHTML = '';
}

function fillInput(text) {
  const input = document.getElementById('userInput');
  input.value = text;
  autoResize(input);
  input.focus();
  const w = document.getElementById('welcome');
  if (w) w.style.display = 'none';
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function scrollDown() {
  const msgs = document.getElementById('messages');
  msgs.scrollTop = msgs.scrollHeight;
}

function appendUserMsg(text) {
  const w = document.getElementById('welcome');
  if (w) w.remove();
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'message-row user';
  row.innerHTML = '<div class="avatar user">&#x1F9D1;</div><div class="bubble"><div style="white-space:pre-wrap">' + esc(text) + '</div></div>';
  msgs.appendChild(row);
  scrollDown();
}

function appendKendrMsg(output, runId) {
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'message-row kendr';
  row.innerHTML = '<div class="avatar kendr">&#x26A1;</div><div class="bubble"><div>' + formatOutput(output) + '</div>' +
    (runId ? '<div class="bubble-meta">Run: ' + esc(runId) + '</div>' : '') + '</div>';
  msgs.appendChild(row);
  scrollDown();
}

function formatOutput(text) {
  if (!text) return '';
  let h = esc(text);
  h = h.replace(/```([\s\S]*?)```/g, '<pre>$1</pre>');
  h = h.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.3);padding:2px 6px;border-radius:4px;font-family:monospace">$1</code>');
  h = h.replace(/\n/g, '<br>');
  return h;
}

function createStreamingRow(runId) {
  const w = document.getElementById('welcome');
  if (w) w.remove();
  const msgs = document.getElementById('messages');
  const row = document.createElement('div');
  row.className = 'message-row kendr';
  row.id = 'stream-row-' + runId;
  row.innerHTML = '<div class="avatar kendr">&#x26A1;</div><div class="bubble" id="stream-bubble-' + runId + '">' +
    '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>' +
    '<div class="streaming-status" id="stream-status-' + runId + '">Starting agents...</div>' +
    '<div class="steps-wrapper" id="stream-steps-' + runId + '"></div>' +
    '<div id="stream-result-' + runId + '"></div></div>';
  msgs.appendChild(row);
  scrollDown();
  return row;
}

function updateStreamStatus(runId, msg) {
  const el = document.getElementById('stream-status-' + runId);
  if (el) el.textContent = msg;
}

function addStreamStep(runId, step) {
  const container = document.getElementById('stream-steps-' + runId);
  if (!container) return;
  const icons = { running: '\u2699\uFE0F', done: '\u2713', failed: '\u2717', completed: '\u2713' };
  const cssClass = step.status || 'running';
  const icon = icons[cssClass] || '\u2699\uFE0F';
  const div = document.createElement('div');
  div.className = 'step-card ' + cssClass;
  div.id = 'step-' + runId + '-' + (step.agent || step.name || Math.random().toString(36).slice(2));
  div.innerHTML = '<div class="step-icon">' + icon + '</div><div class="step-info"><div class="step-name">' +
    esc(step.agent || step.name || 'agent') + '</div>' +
    (step.message ? '<div class="step-desc">' + esc(step.message) + '</div>' : '') + '</div>';
  container.appendChild(div);
  scrollDown();
}

function finalizeStreamRow(runId, output, error, artifactFiles) {
  const row = document.getElementById('stream-row-' + runId);
  if (!row) return;
  const typing = row.querySelector('.typing-indicator');
  if (typing) typing.remove();
  const statusEl = document.getElementById('stream-status-' + runId);
  if (statusEl) statusEl.remove();
  const resultEl = document.getElementById('stream-result-' + runId);
  if (resultEl) {
    if (error) {
      resultEl.innerHTML = '<div class="error-banner" style="margin-top:8px">\u26A0\uFE0F ' + esc(error) + '</div>';
    } else if (output) {
      resultEl.innerHTML = '<div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px">' + formatOutput(output) + '</div>';
    }
    if (artifactFiles && artifactFiles.length > 0) {
      let artHtml = '<div style="margin-top:10px;padding:10px;background:var(--surface2);border:1px solid var(--border);border-radius:8px"><div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">\ud83d\udcc1 Artifact Files</div>';
      artHtml += artifactFiles.map(f => '<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px">' +
        '<span style="color:var(--teal)">\ud83d\udcc4</span>' +
        '<a href="/api/artifacts/download?run_id=' + encodeURIComponent(runId) + '&name=' + encodeURIComponent(f.name) + '" download="' + esc(f.name) + '" style="color:var(--teal);text-decoration:underline">' + esc(f.name) + '</a>' +
        (f.size ? '<span style="color:var(--muted)">(' + (f.size > 1024 ? Math.round(f.size/1024) + ' KB' : f.size + ' B') + ')</span>' : '') + '</div>').join('');
      artHtml += '</div>';
      resultEl.innerHTML += artHtml;
    }
  }
  const meta = document.createElement('div');
  meta.className = 'bubble-meta';
  meta.textContent = 'Run: ' + runId;
  const bubble = document.getElementById('stream-bubble-' + runId);
  if (bubble) bubble.appendChild(meta);
  scrollDown();
}

function openEventStream(runId) {
  if (activeEvtSource) { activeEvtSource.close(); activeEvtSource = null; }
  const evtSrc = new EventSource(API + '/api/stream?run_id=' + encodeURIComponent(runId));
  activeEvtSource = evtSrc;

  evtSrc.addEventListener('status', e => {
    try {
      const d = JSON.parse(e.data);
      updateStreamStatus(runId, d.message || d.status || '');
    } catch(_) {}
  });

  evtSrc.addEventListener('step', e => {
    try { addStreamStep(runId, JSON.parse(e.data)); } catch(_) {}
  });

  evtSrc.addEventListener('result', e => {
    try {
      const d = JSON.parse(e.data);
      const output = d.final_output || d.output || d.draft_response || '';
      updateStreamStatus(runId, 'Completed.');
      finalizeStreamRow(runId, output, '', d.artifact_files || []);
    } catch(_) {}
  });

  evtSrc.addEventListener('error', e => {
    try {
      const d = JSON.parse(e.data);
      finalizeStreamRow(runId, '', d.message || 'Run failed');
    } catch(_) {
      finalizeStreamRow(runId, '', 'Stream error');
    }
    evtSrc.close();
    activeEvtSource = null;
    isRunning = false;
    document.getElementById('sendBtn').disabled = false;
    loadRuns();
  });

  evtSrc.addEventListener('done', e => {
    evtSrc.close();
    activeEvtSource = null;
    isRunning = false;
    document.getElementById('sendBtn').disabled = false;
    loadRuns();
  });

  evtSrc.addEventListener('ping', () => {});

  evtSrc.onerror = () => {
    if (evtSrc.readyState === EventSource.CLOSED) {
      isRunning = false;
      document.getElementById('sendBtn').disabled = false;
    }
  };
}

async function sendMessage() {
  const input = document.getElementById('userInput');
  const text = input.value.trim();
  if (!text || isRunning) return;

  input.value = '';
  autoResize(input);
  isRunning = true;
  document.getElementById('sendBtn').disabled = true;

  appendUserMsg(text);
  const runId = 'ui-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  currentRunId = runId;
  document.getElementById('chatTitle').textContent = text.substring(0, 40) + (text.length > 40 ? '...' : '');
  createStreamingRow(runId);

  try {
    const payload = { text, channel: 'webchat', sender_id: 'ui_user', chat_id: 'web_chat_1', run_id: runId, working_directory: workingDir };
    const resp = await fetch(API + '/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const d = await resp.json();

    if (d.error) {
      finalizeStreamRow(runId, '', d.error + (d.detail ? ': ' + d.detail : ''));
      isRunning = false;
      document.getElementById('sendBtn').disabled = false;
      return;
    }

    if (d.streaming) {
      openEventStream(runId);
    } else {
      const output = d.final_output || d.output || d.draft_response || '(Run completed)';
      finalizeStreamRow(runId, output, '');
      isRunning = false;
      document.getElementById('sendBtn').disabled = false;
      loadRuns();
    }
  } catch(err) {
    finalizeStreamRow(runId, '', 'Request failed: ' + String(err));
    isRunning = false;
    document.getElementById('sendBtn').disabled = false;
  }
}

checkGateway();
loadRuns();
setInterval(checkGateway, 30000);
setInterval(loadRuns, 10000);
</script>
</body>
</html>"""


_SETUP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kendr &#x2014; Setup &amp; Config</title>
<style>
:root { --teal: #00C9A7; --amber: #FFB347; --crimson: #FF4757; --blue: #5352ED; --bg: #0d0f14; --surface: #161b22; --surface2: #1e2530; --border: #2a3140; --text: #e6edf3; --muted: #7d8590; --sidebar-w: 280px; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; }
a { color: var(--teal); }
.sidebar { width: var(--sidebar-w); min-width: var(--sidebar-w); background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: fixed; top: 0; bottom: 0; left: 0; }
.sidebar-header { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
.logo { font-size: 22px; font-weight: 800; color: var(--teal); }
.logo span { color: var(--amber); }
.tagline { font-size: 11px; color: var(--muted); margin-top: 4px; }
.sidebar-nav { padding: 12px 8px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.nav-btn { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; border: none; background: transparent; width: 100%; text-align: left; text-decoration: none; transition: background 0.15s, color 0.15s; }
.nav-btn:hover { background: var(--surface2); color: var(--text); }
.nav-btn.active { background: rgba(0,201,167,0.12); color: var(--teal); }
.nav-btn .icon { font-size: 16px; width: 20px; text-align: center; }
.category-nav { overflow-y: auto; flex: 1; padding: 8px; }
.cat-btn { width: 100%; padding: 8px 12px; background: transparent; border: none; color: var(--muted); font-size: 12px; text-align: left; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.cat-btn:hover { background: var(--surface2); color: var(--text); }
.cat-btn.active { color: var(--teal); font-weight: 600; }
.main { flex: 1; margin-left: var(--sidebar-w); padding: 32px; max-width: 1100px; }
.page-title { font-size: 26px; font-weight: 700; color: var(--text); }
.page-sub { color: var(--muted); font-size: 14px; margin-top: 6px; margin-bottom: 28px; }
.section-title { font-size: 11px; font-weight: 700; color: var(--muted); letter-spacing: 0.08em; text-transform: uppercase; margin: 28px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
.int-card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px; transition: border-color 0.15s; }
.int-card:hover { border-color: var(--blue); }
.int-card.configured { border-color: rgba(0,201,167,0.35); }
.int-card.expanded { border-color: var(--blue); }
.card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; cursor: pointer; }
.card-title-row { flex: 1; }
.card-title { font-size: 15px; font-weight: 600; color: var(--text); }
.card-desc { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.5; }
.card-badges { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }
.badge.ok { background: rgba(0,201,167,0.15); color: var(--teal); }
.badge.warn { background: rgba(255,179,71,0.15); color: var(--amber); }
.badge.err { background: rgba(255,71,87,0.15); color: var(--crimson); }
.toggle { width: 38px; height: 22px; border-radius: 11px; background: var(--border); border: none; cursor: pointer; position: relative; flex-shrink: 0; transition: background 0.2s; }
.toggle::after { content: ''; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform 0.2s; }
.toggle.on { background: var(--teal); }
.toggle.on::after { transform: translateX(16px); }
.card-body { margin-top: 16px; display: none; }
.card-body.open { display: block; }
.field-row { margin-bottom: 12px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 5px; display: flex; align-items: center; gap: 6px; }
.field-desc { font-size: 11px; color: var(--muted); margin-bottom: 5px; }
.secret-badge { font-size: 9px; padding: 1px 5px; border-radius: 3px; background: rgba(255,71,87,0.15); color: var(--crimson); font-weight: 700; }
.required-badge { font-size: 9px; padding: 1px 5px; border-radius: 3px; background: rgba(255,179,71,0.15); color: var(--amber); font-weight: 700; }
.field-input { width: 100%; padding: 9px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 13px; font-family: monospace; transition: border-color 0.15s; outline: none; }
.field-input:focus { border-color: var(--teal); }
.card-actions { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; align-items: center; }
.btn { padding: 8px 16px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; transition: all 0.15s; }
.btn.primary { background: var(--teal); color: #0d0f14; }
.btn.primary:hover { background: #00b396; }
.btn.secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
.save-msg { font-size: 12px; padding: 4px 10px; border-radius: 6px; display: inline-flex; align-items: center; }
.save-msg.ok { background: rgba(0,201,167,0.1); color: var(--teal); }
.save-msg.err { background: rgba(255,71,87,0.1); color: var(--crimson); }
.summary-bar { background: var(--surface2); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 28px; }
.summary-stat { text-align: center; }
.stat-val { font-size: 24px; font-weight: 700; }
.stat-val.teal { color: var(--teal); }
.stat-val.amber { color: var(--amber); }
.stat-val.crimson { color: var(--crimson); }
.stat-label { font-size: 11px; color: var(--muted); margin-top: 2px; }
.env-export { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin-top: 32px; }
.env-export pre { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; max-height: 300px; font-family: monospace; }
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-header"><div class="logo">kendr<span>.</span></div><div class="tagline">Multi-agent intelligence runtime</div></div>
  <div class="sidebar-nav">
    <a href="/" class="nav-btn"><span class="icon">&#x1F4AC;</span> Chat</a>
    <a href="/setup" class="nav-btn active"><span class="icon">&#x2699;&#xFE0F;</span> Setup &amp; Config</a>
    <a href="/runs" class="nav-btn"><span class="icon">&#x1F4CB;</span> Run History</a>
    <a href="/mcp" class="nav-btn"><span class="icon">&#x1F9E9;</span> MCP Servers</a>
  </div>
  <div class="category-nav" id="categoryNav"></div>
</div>
<div class="main">
  <div class="page-title">Setup &amp; Configuration</div>
  <div class="page-sub">Configure integrations, API keys, and runtime settings. All values are stored locally.</div>
  <div class="summary-bar">
    <div class="summary-stat"><div class="stat-val teal" id="statConfigured">-</div><div class="stat-label">Configured</div></div>
    <div class="summary-stat"><div class="stat-val amber" id="statPartial">-</div><div class="stat-label">Partial</div></div>
    <div class="summary-stat"><div class="stat-val crimson" id="statMissing">-</div><div class="stat-label">Missing</div></div>
    <div class="summary-stat"><div class="stat-val" id="statTotal" style="color:var(--muted)">-</div><div class="stat-label">Total</div></div>
  </div>
  <div id="integrations"></div>
  <div class="env-export">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-size:14px;font-weight:600">Export .env</div>
      <button class="btn secondary" onclick="loadEnvExport()">Refresh</button>
    </div>
    <pre id="envExport">Loading...</pre>
  </div>
</div>
<script>
const API = '';
let allComponents = [];

async function loadSetup() {
  try {
    const r = await fetch(API + '/api/setup/overview');
    const d = await r.json();
    allComponents = d.components || [];
    let configured = 0, partial = 0, missing = 0;
    allComponents.forEach(c => {
      const t = c.total_fields || 0, f = c.filled_fields || 0;
      if (t === 0 || f === t) configured++;
      else if (f > 0) partial++;
      else missing++;
    });
    document.getElementById('statConfigured').textContent = configured;
    document.getElementById('statPartial').textContent = partial;
    document.getElementById('statMissing').textContent = missing;
    document.getElementById('statTotal').textContent = allComponents.length;
    renderCategories(d.categories || {});
    renderIntegrations(allComponents);
  } catch(e) {
    document.getElementById('integrations').innerHTML = '<div style="color:var(--crimson);padding:16px">Failed to load: ' + String(e) + '</div>';
  }
}

function slugify(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-'); }

function renderCategories(categories) {
  const nav = document.getElementById('categoryNav');
  nav.innerHTML = '<div style="padding:10px 12px 4px;font-size:10px;font-weight:700;color:var(--muted);letter-spacing:0.08em;text-transform:uppercase">Categories</div>';
  Object.keys(categories).forEach(cat => {
    const btn = document.createElement('button');
    btn.className = 'cat-btn';
    btn.textContent = cat + ' (' + categories[cat].length + ')';
    btn.onclick = () => { document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); document.getElementById('sec-' + slugify(cat))?.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
    nav.appendChild(btn);
  });
}

function renderIntegrations(components) {
  const byCategory = {};
  components.forEach(c => { const cat = c.category || 'Other'; if (!byCategory[cat]) byCategory[cat] = []; byCategory[cat].push(c); });
  const container = document.getElementById('integrations');
  container.innerHTML = '';
  Object.entries(byCategory).forEach(([cat, comps]) => {
    const section = document.createElement('div');
    section.id = 'sec-' + slugify(cat);
    section.innerHTML = '<div class="section-title">' + esc(cat) + '</div>';
    const grid = document.createElement('div');
    grid.className = 'card-grid';
    comps.forEach(c => grid.appendChild(makeCard(c)));
    section.appendChild(grid);
    container.appendChild(section);
  });
}

function makeCard(comp) {
  const total = comp.total_fields || 0, filled = comp.filled_fields || 0;
  const isConfigured = total === 0 || filled === total;
  const isPartial = filled > 0 && filled < total;
  const enabled = comp.enabled !== false;
  const div = document.createElement('div');
  div.className = 'int-card' + (isConfigured ? ' configured' : '');
  div.id = 'card-' + comp.id;
  let statusBadge = total === 0 ? '<span class="badge ok">\u2713 Ready</span>' :
    isConfigured ? '<span class="badge ok">\u2713 Configured</span>' :
    isPartial ? '<span class="badge warn">\u26A1 Partial</span>' :
    '<span class="badge err">\u25CB Not set</span>';
  div.innerHTML = '<div class="card-header" onclick="toggleCard(\'' + esc(comp.id) + '\')">' +
    '<div class="card-title-row"><div class="card-title">' + esc(comp.title) + '</div><div class="card-desc">' + esc(comp.description) + '</div></div>' +
    '<div class="card-badges">' + statusBadge +
    '<button class="toggle ' + (enabled ? 'on' : '') + '" onclick="event.stopPropagation();toggleEnabled(\'' + esc(comp.id) + '\',this)"></button></div></div>' +
    '<div class="card-body" id="body-' + esc(comp.id) + '"></div>';
  return div;
}

async function toggleCard(compId) {
  const body = document.getElementById('body-' + compId);
  if (!body) return;
  const card = document.getElementById('card-' + compId);
  if (body.classList.contains('open')) { body.classList.remove('open'); card.classList.remove('expanded'); return; }
  body.classList.add('open'); card.classList.add('expanded');
  body.innerHTML = '<div style="color:var(--muted);font-size:12px;padding:8px">Loading...</div>';
  try {
    const r = await fetch(API + '/api/setup/component/' + compId);
    const d = await r.json();
    renderCardBody(body, d, compId);
  } catch(e) { body.innerHTML = '<div style="color:var(--crimson);font-size:12px">Failed: ' + String(e) + '</div>'; }
}

function renderCardBody(body, snapshot, compId) {
  const fields = (snapshot.component || {}).fields || [];
  const values = snapshot.values || {};
  const oauthPath = (snapshot.component || {}).oauth_start_path || '';
  let html = '';
  if (fields.length > 0) {
    fields.forEach(f => {
      const val = values[f.key] || '';
      const type = f.secret ? 'password' : 'text';
      const badges = [f.secret ? '<span class="secret-badge">SECRET</span>' : '', f.required ? '<span class="required-badge">REQUIRED</span>' : ''].filter(Boolean).join(' ');
      html += '<div class="field-row"><div class="field-label">' + esc(f.label) + ' ' + badges + '</div>' +
        (f.description ? '<div class="field-desc">' + esc(f.description) + '</div>' : '') +
        '<input class="field-input" type="' + type + '" id="fld-' + esc(compId) + '-' + esc(f.key) + '" value="' + esc(val) + '" placeholder="' + esc(f.key) + '" autocomplete="off"></div>';
    });
  } else {
    html = '<div style="font-size:12px;color:var(--muted);margin-bottom:12px">No configurable fields.</div>';
  }
  let actionsHtml = fields.length > 0 ? '<button class="btn primary" onclick="saveComponent(\'' + esc(compId) + '\')">Save</button>' : '';
  if (oauthPath) {
    actionsHtml += ' <a class="btn oauth" href="' + esc(oauthPath) + '" target="_blank" style="display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;background:rgba(0,201,167,0.15);border:1px solid rgba(0,201,167,0.4);color:var(--teal);font-size:12px;font-weight:600;text-decoration:none;cursor:pointer">\u{1F517} OAuth Connect</a>';
  }
  const testableComponents = ['github'];
  if (testableComponents.includes(compId)) {
    actionsHtml += ' <button class="btn" id="test-btn-' + esc(compId) + '" onclick="testConnection(\'' + esc(compId) + '\')" style="background:rgba(255,179,71,0.12);border:1px solid rgba(255,179,71,0.4);color:var(--amber)">Test connection</button>';
  }
  actionsHtml += '<span class="save-msg" id="save-msg-' + esc(compId) + '" style="display:none"></span>';
  body.innerHTML = html + '<div class="card-actions">' + actionsHtml + '</div>';
}

async function testConnection(compId) {
  const msg = document.getElementById('save-msg-' + compId);
  const btn = document.getElementById('test-btn-' + compId);
  if (btn) btn.disabled = true;
  try {
    const r = await fetch(API + '/api/setup/test-connection/' + compId);
    const d = await r.json();
    if (msg) {
      msg.style.display = 'inline-flex';
      if (d.ok) {
        msg.className = 'save-msg ok';
        msg.textContent = '\u2713 ' + (d.detail || d.login || 'Connected');
      } else {
        msg.className = 'save-msg err';
        msg.textContent = '\u2717 ' + (d.error || 'Connection failed');
      }
      setTimeout(() => { msg.style.display = 'none'; }, 4000);
    }
  } catch(e) {
    if (msg) { msg.style.display = 'inline-flex'; msg.className = 'save-msg err'; msg.textContent = '\u2717 ' + String(e); }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function saveComponent(compId) {
  const r = await fetch(API + '/api/setup/component/' + compId).catch(() => null);
  if (!r) return;
  const d = await r.json();
  const fields = (d.component || {}).fields || [];
  const values = {};
  fields.forEach(f => { const el = document.getElementById('fld-' + compId + '-' + f.key); if (el && !(f.secret && el.value === '********')) values[f.key] = el.value; });
  const msg = document.getElementById('save-msg-' + compId);
  try {
    const resp = await fetch(API + '/api/setup/save', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ component_id: compId, values }) });
    const res = await resp.json();
    if (res.error) throw new Error(res.error);
    if (msg) { msg.style.display = 'inline-flex'; msg.className = 'save-msg ok'; msg.textContent = '\u2713 Saved'; setTimeout(() => { msg.style.display = 'none'; }, 2500); }
    loadSetup();
  } catch(e) { if (msg) { msg.style.display = 'inline-flex'; msg.className = 'save-msg err'; msg.textContent = '\u2717 ' + String(e); } }
}

async function toggleEnabled(compId, btn) {
  const newState = !btn.classList.contains('on');
  try {
    await fetch(API + '/api/setup/enabled', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ component_id: compId, enabled: newState }) });
    btn.classList.toggle('on', newState);
  } catch(e) { alert('Failed: ' + e); }
}

async function loadEnvExport() {
  try {
    const r = await fetch(API + '/api/setup/env-export');
    const d = await r.json();
    document.getElementById('envExport').textContent = (d.lines || []).join('\n') || '# No configuration stored yet.';
  } catch(e) { document.getElementById('envExport').textContent = '# Error: ' + e; }
}

function esc(s) { return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
loadSetup();
loadEnvExport();
</script>
</body>
</html>"""


_MCP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kendr &mdash; MCP Servers</title>
<style>
:root { --teal: #00C9A7; --amber: #FFB347; --crimson: #FF4757; --purple: #A78BFA; --bg: #0d0f14; --surface: #161b22; --surface2: #1e2530; --surface3: #252d3a; --border: #2a3140; --text: #e6edf3; --muted: #7d8590; --sidebar-w: 280px; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; }
.sidebar { width: var(--sidebar-w); min-width: var(--sidebar-w); background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: fixed; top: 0; bottom: 0; left: 0; }
.sidebar-header { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
.logo { font-size: 22px; font-weight: 800; color: var(--teal); }
.logo span { color: var(--amber); }
.tagline { font-size: 11px; color: var(--muted); margin-top: 4px; }
.sidebar-nav { padding: 12px 8px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.nav-btn { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; border: none; background: transparent; width: 100%; text-align: left; text-decoration: none; transition: background 0.15s, color 0.15s; }
.nav-btn:hover { background: var(--surface2); color: var(--text); }
.nav-btn.active { background: rgba(167,139,250,0.12); color: var(--purple); }
.nav-btn .icon { font-size: 16px; width: 20px; text-align: center; }
.main { flex: 1; margin-left: var(--sidebar-w); padding: 32px; max-width: 960px; }
.page-title { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.page-subtitle { font-size: 13px; color: var(--muted); margin-bottom: 28px; }
/* Cards */
.section-title { font-size: 13px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; margin: 28px 0 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; margin-bottom: 12px; }
.card-header { display: flex; align-items: center; gap: 12px; }
.server-name { font-size: 15px; font-weight: 600; flex: 1; }
.server-meta { font-size: 12px; color: var(--muted); margin-top: 3px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge.connected { background: rgba(0,201,167,0.15); color: var(--teal); }
.badge.error { background: rgba(255,71,87,0.15); color: var(--crimson); }
.badge.unknown { background: rgba(125,133,144,0.15); color: var(--muted); }
.badge.http { background: rgba(0,201,167,0.1); color: var(--teal); }
.badge.stdio { background: rgba(167,139,250,0.1); color: var(--purple); }
.tools-toggle { background: none; border: 1px solid var(--border); color: var(--teal); border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 12px; }
.tools-toggle:hover { background: var(--surface2); }
.btn { padding: 8px 16px; border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer; border: none; transition: opacity 0.15s; }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--teal); color: #0d0f14; }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-danger { background: rgba(255,71,87,0.12); color: var(--crimson); border: 1px solid rgba(255,71,87,0.3); }
.btn-ghost { background: none; color: var(--muted); border: 1px solid var(--border); }
.tool-list { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 12px; display: none; }
.tool-list.open { display: block; }
.tool-item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border); }
.tool-item:last-child { border-bottom: none; }
.tool-name { font-family: monospace; font-size: 13px; color: var(--teal); font-weight: 600; min-width: 160px; }
.tool-desc { font-size: 12px; color: var(--muted); flex: 1; }
/* Add form */
.form-section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 24px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
.form-full { margin-bottom: 14px; }
label { display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.05em; }
input, select, textarea { width: 100%; background: var(--surface2); border: 1px solid var(--border); border-radius: 7px; padding: 9px 12px; color: var(--text); font-size: 13px; outline: none; transition: border-color 0.15s; }
input:focus, select:focus, textarea:focus { border-color: var(--teal); }
textarea { resize: vertical; min-height: 60px; font-family: inherit; }
.form-actions { display: flex; gap: 10px; align-items: center; }
.msg { font-size: 12px; padding: 6px 10px; border-radius: 6px; }
.msg.ok { background: rgba(0,201,167,0.1); color: var(--teal); }
.msg.err { background: rgba(255,71,87,0.1); color: var(--crimson); }
/* Scaffold */
.scaffold-box { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; position: relative; }
.scaffold-box pre { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 12px; color: #b5c4de; white-space: pre-wrap; word-break: break-word; max-height: 420px; overflow-y: auto; }
.copy-btn { position: absolute; top: 10px; right: 10px; background: var(--surface); border: 1px solid var(--border); color: var(--teal); border-radius: 6px; padding: 4px 10px; font-size: 11px; cursor: pointer; }
.copy-btn:hover { background: var(--surface2); }
/* Toggle switch */
.toggle { position: relative; display: inline-block; width: 34px; height: 20px; }
.toggle input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; inset: 0; background: var(--border); border-radius: 20px; transition: 0.2s; }
.slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: 0.2s; }
input:checked + .slider { background: var(--teal); }
input:checked + .slider:before { transform: translateX(14px); }
.disc-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--teal); border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }
.error-box { background: rgba(255,71,87,0.07); border: 1px solid rgba(255,71,87,0.25); border-radius: 6px; padding: 8px 12px; font-size: 12px; color: var(--crimson); margin-top: 10px; }
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-header"><div class="logo">kendr<span>.</span></div><div class="tagline">Multi-agent intelligence runtime</div></div>
  <div class="sidebar-nav">
    <a href="/" class="nav-btn"><span class="icon">&#x1F4AC;</span> Chat</a>
    <a href="/setup" class="nav-btn"><span class="icon">&#x2699;&#xFE0F;</span> Setup &amp; Config</a>
    <a href="/runs" class="nav-btn"><span class="icon">&#x1F4CB;</span> Run History</a>
    <a href="/mcp" class="nav-btn active"><span class="icon">&#x1F9E9;</span> MCP Servers</a>
  </div>
</div>
<div class="main">
  <div class="page-title">MCP Servers</div>
  <div class="page-subtitle">Connect kendr to any MCP server &mdash; kendr acts as the client, just like Cursor. Tools are auto-discovered.</div>

  <!-- Add server form -->
  <div class="section-title">Connect a New MCP Server</div>
  <div class="form-section">
    <div class="form-row">
      <div>
        <label>Server Name</label>
        <input type="text" id="addName" placeholder="e.g. My Research Server">
      </div>
      <div>
        <label>Type</label>
        <select id="addType" onchange="toggleTypeHint()">
          <option value="http">HTTP / SSE</option>
          <option value="stdio">Stdio (shell command)</option>
        </select>
      </div>
    </div>
    <div class="form-full">
      <label id="connLabel">Connection URL</label>
      <input type="text" id="addConn" placeholder="http://localhost:8000/mcp">
      <div id="connHint" style="font-size:11px;color:var(--muted);margin-top:4px">HTTP or SSE endpoint — e.g. http://localhost:8000/mcp</div>
    </div>
    <div class="form-full">
      <label>Description (optional)</label>
      <textarea id="addDesc" rows="2" placeholder="What does this server provide?"></textarea>
    </div>
    <div class="form-actions">
      <button class="btn btn-primary" onclick="addServer()">Connect &amp; Discover Tools</button>
      <span id="addMsg"></span>
    </div>
  </div>

  <!-- Registered servers -->
  <div class="section-title">Registered Servers</div>
  <div id="serverList"><div style="color:var(--muted);font-size:13px">Loading...</div></div>

  <!-- Scaffold section -->
  <div class="section-title" style="margin-top:36px">How to Build Your Own MCP Server</div>
  <p style="font-size:13px;color:var(--muted);margin-bottom:14px">
    Any Python function decorated with <code style="color:var(--teal)">@mcp.tool</code> becomes a discoverable tool.
    Run the server, then add it above. Uses <a href="https://github.com/jlowin/fastmcp" target="_blank" style="color:var(--teal)">FastMCP</a>.
  </p>
  <div class="scaffold-box">
    <button class="copy-btn" onclick="copyScaffold()">Copy</button>
    <pre id="scaffoldCode">Loading...</pre>
  </div>
  <p style="font-size:12px;color:var(--muted);margin-top:10px">
    The full example is at <code style="color:var(--teal)">mcp_servers/example_fastmcp_server.py</code> &mdash; run with <code style="color:var(--teal)">python mcp_servers/example_fastmcp_server.py</code>
  </p>
</div>

<script>
const API = '';

function toggleTypeHint() {
  const t = document.getElementById('addType').value;
  const lbl = document.getElementById('connLabel');
  const inp = document.getElementById('addConn');
  const hint = document.getElementById('connHint');
  if (t === 'stdio') {
    lbl.textContent = 'Shell Command';
    inp.placeholder = 'python mcp_servers/my_server.py';
    hint.textContent = 'Shell command to launch the stdio MCP server process';
  } else {
    lbl.textContent = 'Connection URL';
    inp.placeholder = 'http://localhost:8000/mcp';
    hint.textContent = 'HTTP or SSE endpoint — e.g. http://localhost:8000/mcp';
  }
}

async function addServer() {
  const name = document.getElementById('addName').value.trim();
  const type = document.getElementById('addType').value;
  const conn = document.getElementById('addConn').value.trim();
  const desc = document.getElementById('addDesc').value.trim();
  const msg = document.getElementById('addMsg');
  if (!name) { showMsg(msg, 'Server name is required', 'err'); return; }
  if (!conn) { showMsg(msg, 'Connection is required', 'err'); return; }
  showMsg(msg, '<span class="disc-spinner"></span> Connecting and discovering tools…', 'ok');
  try {
    const r = await fetch(API + '/api/mcp/servers', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name, type, connection: conn, description: desc })
    });
    const d = await r.json();
    if (d.ok || d.server_id) {
      showMsg(msg, '&#x2713; Connected — ' + (d.tool_count || 0) + ' tool(s) discovered', 'ok');
      document.getElementById('addName').value = '';
      document.getElementById('addConn').value = '';
      document.getElementById('addDesc').value = '';
      await loadServers();
    } else {
      showMsg(msg, 'Error: ' + (d.error || JSON.stringify(d)), 'err');
    }
  } catch(e) { showMsg(msg, 'Request failed: ' + e, 'err'); }
}

function showMsg(el, text, cls) {
  el.className = 'msg ' + cls;
  el.innerHTML = text;
}

async function loadServers() {
  const box = document.getElementById('serverList');
  try {
    const r = await fetch(API + '/api/mcp/servers');
    const servers = await r.json();
    if (!servers.length) {
      box.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:16px 0">No servers registered yet. Add one above.</div>';
      return;
    }
    box.innerHTML = servers.map(s => renderServer(s)).join('');
  } catch(e) {
    box.innerHTML = '<div style="color:var(--crimson);font-size:13px">Failed to load servers: ' + e + '</div>';
  }
}

function renderServer(s) {
  const statusCls = s.status === 'connected' ? 'connected' : s.status === 'error' ? 'error' : 'unknown';
  const statusLabel = s.status === 'connected' ? '&#x25CF; Connected' : s.status === 'error' ? '&#x25CF; Error' : '&#x25CB; Unknown';
  const typeBadge = '<span class="badge ' + s.type + '">' + (s.type === 'http' ? 'HTTP' : 'stdio') + '</span>';
  const lastDisc = s.last_discovered ? 'Last discovered: ' + s.last_discovered.replace('T',' ').replace('Z','') + ' UTC' : 'Not yet discovered';
  const toolCount = s.tool_count || 0;
  const toolsId = 'tools-' + s.id;
  const toolRows = (s.tools || []).map(t =>
    '<div class="tool-item"><span class="tool-name">' + esc(t.name) + '</span><span class="tool-desc">' + esc(t.description || '—') + '</span></div>'
  ).join('');
  const errorBox = (s.error && s.status === 'error') ? '<div class="error-box">&#x26A0; ' + esc(s.error) + '</div>' : '';
  return `<div class="card" id="srv-${s.id}">
  <div class="card-header">
    <div style="flex:1">
      <div class="server-name">${esc(s.name)} ${typeBadge}</div>
      <div class="server-meta">${esc(s.connection)} &mdash; <span class="badge ${statusCls}">${statusLabel}</span> &mdash; ${toolCount} tool${toolCount !== 1 ? 's' : ''} &mdash; ${esc(lastDisc)}</div>
      ${s.description ? '<div class="server-meta" style="margin-top:2px">' + esc(s.description) + '</div>' : ''}
    </div>
    <label class="toggle" title="${s.enabled ? 'Enabled' : 'Disabled'}">
      <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="toggleServer('${s.id}', this.checked)">
      <span class="slider"></span>
    </label>
  </div>
  ${errorBox}
  <div style="display:flex;gap:8px;margin-top:12px;align-items:center">
    <button class="btn btn-sm btn-ghost" onclick="discoverTools('${s.id}', this)">&#x1F50D; Re-discover Tools</button>
    ${toolCount > 0 ? '<button class="tools-toggle" onclick="toggleTools(\'' + toolsId + '\', this)">\u25bc ' + toolCount + ' tools</button>' : ''}
    <button class="btn btn-sm btn-danger" onclick="removeServer('${s.id}')">Remove</button>
  </div>
  <div class="tool-list" id="${toolsId}">
    ${toolRows || '<div style="color:var(--muted);font-size:12px">No tools discovered yet. Click Re-discover.</div>'}
  </div>
</div>`;
}

function toggleTools(id, btn) {
  const el = document.getElementById(id);
  el.classList.toggle('open');
  btn.textContent = el.classList.contains('open') ? '\u25b2 hide tools' : '\u25bc ' + btn.textContent.replace(/[▼▲]\s*/,'');
}

async function discoverTools(serverId, btn) {
  const orig = btn.textContent;
  btn.disabled = true;
  btn.innerHTML = '<span class="disc-spinner"></span> Discovering…';
  try {
    const r = await fetch(API + '/api/mcp/servers/' + serverId + '/discover', { method: 'POST' });
    const d = await r.json();
    await loadServers();
  } catch(e) { alert('Discovery failed: ' + e); }
  btn.disabled = false;
  btn.textContent = orig;
}

async function removeServer(serverId) {
  if (!confirm('Remove this MCP server?')) return;
  try {
    await fetch(API + '/api/mcp/servers/' + serverId + '/remove', { method: 'POST' });
    await loadServers();
  } catch(e) { alert('Remove failed: ' + e); }
}

async function toggleServer(serverId, enabled) {
  try {
    await fetch(API + '/api/mcp/servers/' + serverId + '/toggle', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ enabled })
    });
  } catch(e) { console.warn('Toggle failed', e); }
}

async function loadScaffold() {
  try {
    const r = await fetch(API + '/api/mcp/scaffold');
    const d = await r.json();
    document.getElementById('scaffoldCode').textContent = d.code || '';
  } catch(e) {
    document.getElementById('scaffoldCode').textContent = '# Could not load scaffold: ' + e;
  }
}

function copyScaffold() {
  const code = document.getElementById('scaffoldCode').textContent;
  navigator.clipboard.writeText(code).then(() => {
    const btn = document.querySelector('.copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1800);
  });
}

function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

loadServers();
loadScaffold();
</script>
</body>
</html>"""


_RUNS_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kendr &#x2014; Run History</title>
<style>
:root { --teal: #00C9A7; --amber: #FFB347; --crimson: #FF4757; --bg: #0d0f14; --surface: #161b22; --surface2: #1e2530; --border: #2a3140; --text: #e6edf3; --muted: #7d8590; --sidebar-w: 280px; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: flex; }
.sidebar { width: var(--sidebar-w); min-width: var(--sidebar-w); background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: fixed; top: 0; bottom: 0; left: 0; }
.sidebar-header { padding: 20px 16px 12px; border-bottom: 1px solid var(--border); }
.logo { font-size: 22px; font-weight: 800; color: var(--teal); }
.logo span { color: var(--amber); }
.tagline { font-size: 11px; color: var(--muted); margin-top: 4px; }
.sidebar-nav { padding: 12px 8px; display: flex; flex-direction: column; gap: 4px; }
.nav-btn { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; color: var(--muted); cursor: pointer; border: none; background: transparent; width: 100%; text-align: left; text-decoration: none; transition: background 0.15s, color 0.15s; }
.nav-btn:hover { background: var(--surface2); color: var(--text); }
.nav-btn.active { background: rgba(0,201,167,0.12); color: var(--teal); }
.nav-btn .icon { font-size: 16px; width: 20px; text-align: center; }
.main { flex: 1; margin-left: var(--sidebar-w); padding: 32px; }
.page-title { font-size: 26px; font-weight: 700; margin-bottom: 24px; }
.run-table { width: 100%; border-collapse: collapse; }
.run-table th { text-align: left; padding: 10px 16px; font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid var(--border); }
.run-table td { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px; vertical-align: top; }
.run-table tr:hover td { background: var(--surface); }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge.completed { background: rgba(0,201,167,0.15); color: var(--teal); }
.badge.failed { background: rgba(255,71,87,0.15); color: var(--crimson); }
.badge.running { background: rgba(255,179,71,0.15); color: var(--amber); }
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-header"><div class="logo">kendr<span>.</span></div><div class="tagline">Multi-agent intelligence runtime</div></div>
  <div class="sidebar-nav">
    <a href="/" class="nav-btn"><span class="icon">&#x1F4AC;</span> Chat</a>
    <a href="/setup" class="nav-btn"><span class="icon">&#x2699;&#xFE0F;</span> Setup &amp; Config</a>
    <a href="/runs" class="nav-btn active"><span class="icon">&#x1F4CB;</span> Run History</a>
    <a href="/mcp" class="nav-btn"><span class="icon">&#x1F9E9;</span> MCP Servers</a>
  </div>
</div>
<div class="main">
  <div class="page-title">Run History</div>
  <table class="run-table">
    <thead><tr><th>Query</th><th>Run ID</th><th>Status</th><th>Agent</th><th>Created</th><th>Files</th></tr></thead>
    <tbody id="runBody"><tr><td colspan="5" style="color:var(--muted);text-align:center;padding:24px">Loading...</td></tr></tbody>
  </table>
</div>
<script>
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
async function load() {
  try {
    const r = await fetch('/api/runs');
    const runs = await r.json();
    const body = document.getElementById('runBody');
    if (!runs || !runs.length) { body.innerHTML = '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:24px">No runs yet. Start a chat to create your first run.</td></tr>'; return; }
    body.innerHTML = runs.map(run => {
      const status = (run.status || 'completed').toLowerCase();
      const rid = run.run_id || '';
      return '<tr><td style="max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="' + esc(run.query||run.text||'') + '">' + esc((run.query||run.text||'\u2014').substring(0,70)) + '</td><td style="font-family:monospace;font-size:11px;color:var(--muted)">' + esc(rid) + '</td><td><span class="badge ' + status + '">' + status + '</span></td><td style="color:var(--muted)">' + esc(run.last_agent||'') + '</td><td style="color:var(--muted);white-space:nowrap">' + esc(run.created_at||'') + '</td><td><button onclick="showArtifacts(\'' + rid + '\', this)" style="background:none;border:1px solid var(--border);color:var(--teal);border-radius:6px;padding:3px 8px;cursor:pointer;font-size:11px">\ud83d\udcc1</button></td></tr>';
    }).join('');
  } catch(e) { document.getElementById('runBody').innerHTML = '<tr><td colspan="6" style="color:var(--crimson)">Error: ' + String(e) + '</td></tr>'; }
}
async function showArtifacts(runId, btn) {
  btn.disabled = true;
  try {
    const r = await fetch('/api/runs/' + runId + '/artifacts');
    const d = await r.json();
    const files = (d.files || []);
    if (!files.length) { btn.textContent = '\u2205 none'; return; }
    const row = btn.closest('tr');
    const extra = document.createElement('tr');
    extra.innerHTML = '<td colspan="6" style="background:var(--surface2);padding:10px 16px"><strong style="font-size:11px;color:var(--muted)">ARTIFACTS</strong> ' +
      files.map(f => '<a href="/api/artifacts/download?run_id=' + encodeURIComponent(runId) + '&name=' + encodeURIComponent(f.name) + '" download="' + esc(f.name) + '" style="color:var(--teal);text-decoration:underline;margin-right:12px;font-size:12px">' + esc(f.name) + '</a>').join('') + '</td>';
    row.insertAdjacentElement('afterend', extra);
    btn.style.display = 'none';
  } catch(e) { btn.disabled = false; }
}
load();
</script>
</body>
</html>"""


class KendrUIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    _CORS_SAFE_PREFIXES = ("/api/stream", "/stream")

    def _send(self, status: int, content_type: str, body: bytes, cors: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        path = getattr(self, "path", "")
        cors = any(path.startswith(p) for p in self._CORS_SAFE_PREFIXES)
        self._send(status, "application/json; charset=utf-8", body, cors=cors)

    def _html(self, status: int, content: str) -> None:
        self._send(status, "text/html; charset=utf-8", content.encode("utf-8"), cors=False)

    def do_OPTIONS(self):
        self.send_response(200)
        path = getattr(self, "path", "")
        if any(path.startswith(p) for p in self._CORS_SAFE_PREFIXES):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path in ("/", "/chat"):
            self._html(200, _CHAT_HTML)
            return
        if path == "/setup":
            self._html(200, _SETUP_HTML)
            return
        if path == "/runs":
            self._html(200, _RUNS_HTML)
            return
        if path == "/mcp":
            self._html(200, _MCP_HTML)
            return
        if path == "/api/health":
            self._json(200, {"service": "kendr-ui", "status": "ok"})
            return
        if path == "/api/gateway/status":
            working_dir = os.getenv("KENDR_WORKING_DIR", "").strip()
            self._json(200, {
                "online": _gateway_ready(),
                "gateway_url": _gateway_url(),
                "working_dir": working_dir,
                "ui_port": _UI_PORT,
            })
            return
        if path == "/api/runs":
            try:
                runs = _gateway_get("/runs", timeout=5.0)
            except Exception:
                runs = []
            self._json(200, runs)
            return
        if path == "/api/artifacts/download":
            params = parse_qs(parsed.query or "")
            run_id = (params.get("run_id") or [""])[0]
            name = (params.get("name") or [""])[0]
            if not run_id or not name or "/" in name or "\\" in name or name.startswith("."):
                self._json(400, {"error": "invalid_request"})
                return
            try:
                run_row = _db_get_run(run_id)
                output_dir = run_row.get("run_output_dir", "") if run_row else ""
            except Exception:
                output_dir = ""
            if not output_dir:
                self._json(404, {"error": "run_not_found_or_no_output_dir"})
                return
            file_path = os.path.join(output_dir, name)
            if not os.path.isfile(file_path):
                self._json(404, {"error": "file_not_found", "name": name})
                return
            try:
                with open(file_path, "rb") as fh:
                    data = fh.read()
                import mimetypes
                mime_type, _ = mimetypes.guess_type(file_path)
                content_type = mime_type or "application/octet-stream"
                safe_name = os.path.basename(file_path)
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return
        if path.startswith("/api/runs/") and path.endswith("/artifacts"):
            run_id = path[len("/api/runs/"):-len("/artifacts")]
            db_artifacts, file_list = [], []
            output_dir = ""
            try:
                run_row = _db_get_run(run_id)
                if run_row:
                    output_dir = run_row.get("run_output_dir", "")
                db_artifacts, file_list = _collect_artifacts(run_id, output_dir)
            except Exception:
                pass
            self._json(200, {
                "run_id": run_id,
                "output_dir": output_dir,
                "artifacts": db_artifacts,
                "files": file_list,
            })
            return
        if path.startswith("/api/runs/"):
            run_id = path[len("/api/runs/"):]
            try:
                data = _gateway_get(f"/runs/{run_id}")
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return
            self._json(200, data)
            return
        if path == "/api/setup/overview":
            try:
                apply_setup_env_defaults()
                overview = setup_overview()
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return
            self._json(200, overview)
            return
        if path.startswith("/api/setup/component/"):
            comp_id = path[len("/api/setup/component/"):]
            try:
                snap = get_setup_component_snapshot(comp_id)
            except Exception as exc:
                self._json(500, {"error": str(exc)})
                return
            if not snap:
                self._json(404, {"error": "component_not_found"})
                return
            snap = dict(snap)
            snap.pop("raw_values", None)
            oauth_path = _OAUTH_PATH_MAP.get(comp_id, "")
            if oauth_path and snap.get("component") is not None:
                parts = oauth_path.strip("/").split("/")
                provider = parts[1] if len(parts) >= 2 else ""
                snap["component"] = dict(snap["component"])
                if provider:
                    snap["component"]["oauth_start_path"] = f"/api/oauth/{provider}/start"
                    snap["component"]["oauth_provider"] = provider
            self._json(200, snap)
            return
        if path == "/api/setup/env-export":
            try:
                lines = export_env_lines(include_secrets=False)
            except Exception as exc:
                lines = []
            self._json(200, {"lines": lines})
            return
        if path.startswith("/api/setup/test-connection/"):
            comp_id = path[len("/api/setup/test-connection/"):]
            self._handle_test_connection(comp_id)
            return
        if path.startswith("/api/oauth/") and path.endswith("/start"):
            provider = path[len("/api/oauth/"):-len("/start")]
            self._handle_oauth_start(provider)
            return
        if path.startswith("/api/oauth/") and path.endswith("/callback"):
            provider = path[len("/api/oauth/"):-len("/callback")]
            self._handle_oauth_callback(provider, parse_qs(parsed.query or ""))
            return
        if path == "/api/mcp/servers":
            if not _HAS_MCP_MANAGER:
                self._json(503, {"error": "MCP manager not available"})
                return
            try:
                self._json(200, _mcp_list_servers())
            except Exception as exc:
                self._json(500, {"error": str(exc)})
            return
        if path == "/api/mcp/scaffold":
            code = _MCP_SCAFFOLD_CODE if _HAS_MCP_MANAGER else "# fastmcp not installed"
            self._json(200, {"code": code})
            return
        if path in ("/api/stream", "/stream"):
            params = parse_qs(parsed.query or "")
            run_id = (params.get("run_id") or [""])[0]
            if not run_id:
                self._json(400, {"error": "missing_run_id"})
                return
            self._handle_sse(run_id)
            return
        self._json(404, {"error": "not_found", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length)
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            self._json(400, {"error": "invalid_json", "detail": str(exc)})
            return

        if path == "/api/chat":
            self._handle_chat(body)
            return
        if path == "/api/setup/save":
            self._handle_setup_save(body)
            return
        if path == "/api/setup/enabled":
            self._handle_setup_enabled(body)
            return
        if path == "/api/mcp/servers":
            self._handle_mcp_add(body)
            return
        if path.startswith("/api/mcp/servers/"):
            rest = path[len("/api/mcp/servers/"):]
            if rest.endswith("/discover"):
                server_id = rest[:-len("/discover")]
                self._handle_mcp_discover(server_id)
            elif rest.endswith("/remove"):
                server_id = rest[:-len("/remove")]
                self._handle_mcp_remove(server_id)
            elif rest.endswith("/toggle"):
                server_id = rest[:-len("/toggle")]
                self._handle_mcp_toggle(server_id, body)
            else:
                self._json(404, {"error": "not_found"})
            return
        self._json(404, {"error": "not_found"})

    def _handle_chat(self, body: dict) -> None:
        text = str(body.get("text") or body.get("message") or "").strip()
        if not text:
            self._json(400, {"error": "missing_text"})
            return
        if not _gateway_ready():
            self._json(503, {
                "error": "Gateway not running",
                "detail": "Start it with: kendr gateway start",
            })
            return
        working_directory = str(
            body.get("working_directory") or os.getenv("KENDR_WORKING_DIR", "")
        ).strip()
        payload = {
            "text": text,
            "channel": str(body.get("channel", "webchat")),
            "sender_id": str(body.get("sender_id", "ui_user")),
            "chat_id": str(body.get("chat_id", "web_chat_1")),
        }
        if working_directory:
            payload["working_directory"] = working_directory
        run_id = str(body.get("run_id") or "").strip() or f"ui-{uuid.uuid4().hex[:8]}"
        payload["run_id"] = run_id

        q: "queue.Queue[dict]" = queue.Queue()
        with _pending_lock:
            _run_event_queues[run_id] = q
            _pending_runs[run_id] = {"status": "running"}

        _start_run_background(run_id, payload)
        self._json(200, {"run_id": run_id, "streaming": True, "status": "started"})

    def _handle_sse(self, run_id: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def write_event(event_type: str, data: dict) -> bool:
            try:
                msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
                self.wfile.write(msg.encode("utf-8"))
                self.wfile.flush()
                return True
            except Exception:
                return False

        with _pending_lock:
            q = _run_event_queues.get(run_id)
            run_data = _pending_runs.get(run_id)

        if q is None and run_data:
            write_event("result", run_data.get("result", {}))
            write_event("done", {"run_id": run_id})
            return
        if q is None:
            write_event("error", {"message": "Run not found"})
            return

        write_event("status", {"status": "connected", "run_id": run_id})
        while True:
            try:
                event = q.get(timeout=1.0)
                if not write_event(event["type"], event["data"]):
                    break
                if event["type"] == "done":
                    with _pending_lock:
                        _run_event_queues.pop(run_id, None)
                    break
            except queue.Empty:
                if not write_event("ping", {"ts": int(time.time())}):
                    break

    def _handle_oauth_start(self, provider: str) -> None:
        if not _HAS_OAUTH:
            self._html(503, "<h1>OAuth not available</h1><p>kendr.providers module not loaded.</p>")
            return
        try:
            missing: list[str] = []
            if provider == "google":
                config = build_google_oauth_config()
                for k in ("client_id", "client_secret", "redirect_uri", "scopes"):
                    if not str(config.get(k, "")).strip():
                        missing.append({"client_id": "GOOGLE_CLIENT_ID", "client_secret": "GOOGLE_CLIENT_SECRET",
                                        "redirect_uri": "GOOGLE_REDIRECT_URI", "scopes": "GOOGLE_OAUTH_SCOPES"}.get(k, k))
            elif provider == "microsoft":
                config = build_microsoft_oauth_config()
                for k in ("client_id", "client_secret", "redirect_uri", "scopes"):
                    if not str(config.get(k, "")).strip():
                        missing.append({"client_id": "MICROSOFT_CLIENT_ID", "client_secret": "MICROSOFT_CLIENT_SECRET",
                                        "redirect_uri": "MICROSOFT_REDIRECT_URI", "scopes": "MICROSOFT_OAUTH_SCOPES"}.get(k, k))
            elif provider == "slack":
                config = build_slack_oauth_config()
                for k in ("client_id", "client_secret", "redirect_uri", "scopes"):
                    if not str(config.get(k, "")).strip():
                        missing.append({"client_id": "SLACK_CLIENT_ID", "client_secret": "SLACK_CLIENT_SECRET",
                                        "redirect_uri": "SLACK_REDIRECT_URI", "scopes": "SLACK_OAUTH_SCOPES"}.get(k, k))
            else:
                self._html(400, f"<h1>Unknown provider: {_html.escape(provider)}</h1>")
                return
            if missing:
                body_txt = (
                    f"<h1>{_html.escape(provider.title())} OAuth not configured</h1>"
                    "<p>Set the following environment variables before connecting:</p>"
                    f"<pre>{_html.escape(chr(10).join(missing))}</pre>"
                    '<p><a href="/setup">Return to Setup</a></p>'
                )
                self._html(400, body_txt)
                return
            state_token = issue_oauth_state_token()
            _OAUTH_PENDING_STATES[state_token] = provider
            if provider == "google":
                url = build_google_oauth_start_url(state_token)
            elif provider == "microsoft":
                url = build_microsoft_oauth_start_url(state_token)
            else:
                url = build_slack_oauth_start_url(state_token)
            self.send_response(302)
            self.send_header("Location", url)
            self.end_headers()
        except Exception as exc:
            self._html(500, f"<h1>OAuth error</h1><p>{_html.escape(str(exc))}</p>")

    def _handle_oauth_callback(self, provider: str, query: dict) -> None:
        if not _HAS_OAUTH:
            self._html(503, "<h1>OAuth not available</h1>")
            return
        state_token = (query.get("state") or [""])[0]
        code = (query.get("code") or [""])[0]
        error = (query.get("error") or [""])[0]
        if error:
            self._html(400, f"<h1>OAuth failed</h1><p>{_html.escape(error)}</p>")
            return
        if not code:
            self._html(400, "<h1>OAuth failed</h1><p>Missing authorization code.</p>")
            return
        if _OAUTH_PENDING_STATES.get(state_token) != provider:
            self._html(400, "<h1>OAuth failed</h1><p>Invalid or expired state token.</p>")
            return
        try:
            if provider == "google":
                exchange_google_oauth_code(code)
            elif provider == "microsoft":
                exchange_microsoft_oauth_code(code)
            elif provider == "slack":
                exchange_slack_oauth_code(code)
            else:
                self._html(400, f"<h1>Unknown provider: {_html.escape(provider)}</h1>")
                return
            _OAUTH_PENDING_STATES.pop(state_token, None)
            self._html(200, (
                f"<h1>{_html.escape(provider.title())} connected</h1>"
                "<p>Tokens saved to the kendr setup database.</p>"
                '<p><a href="/setup">Return to Setup</a></p>'
            ))
        except Exception as exc:
            self._html(500, f"<h1>OAuth failed</h1><p>{_html.escape(str(exc))}</p>")

    def _handle_setup_save(self, body: dict) -> None:
        comp_id = str(body.get("component_id", "")).strip()
        values = body.get("values", {})
        if not comp_id:
            self._json(400, {"error": "missing_component_id"})
            return
        try:
            result = save_component_values(comp_id, values)
            apply_setup_env_defaults()
            safe_result = dict(result)
            safe_result.pop("raw_values", None)
            self._json(200, {"saved": True, "snapshot": safe_result})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_setup_enabled(self, body: dict) -> None:
        comp_id = str(body.get("component_id", "")).strip()
        enabled = bool(body.get("enabled", True))
        if not comp_id:
            self._json(400, {"error": "missing_component_id"})
            return
        try:
            set_component_enabled(comp_id, enabled)
            self._json(200, {"component_id": comp_id, "enabled": enabled})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_mcp_add(self, body: dict) -> None:
        if not _HAS_MCP_MANAGER:
            self._json(503, {"error": "MCP manager not available"})
            return
        name = str(body.get("name", "")).strip()
        connection = str(body.get("connection", "")).strip()
        server_type = str(body.get("type", "http")).strip()
        description = str(body.get("description", "")).strip()
        if not name or not connection:
            self._json(400, {"error": "name and connection are required"})
            return
        try:
            entry = _mcp_add_server(name, connection, server_type, description)
            server_id = entry["id"]
            result = _mcp_discover_tools(server_id)
            result["server"] = _mcp_get_server(server_id)
            self._json(200, result)
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_mcp_discover(self, server_id: str) -> None:
        if not _HAS_MCP_MANAGER:
            self._json(503, {"error": "MCP manager not available"})
            return
        server_id = server_id.strip().rstrip("/")
        if not server_id:
            self._json(400, {"error": "missing_server_id"})
            return
        try:
            result = _mcp_discover_tools(server_id)
            self._json(200, result)
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_mcp_remove(self, server_id: str) -> None:
        if not _HAS_MCP_MANAGER:
            self._json(503, {"error": "MCP manager not available"})
            return
        server_id = server_id.strip().rstrip("/")
        try:
            removed = _mcp_remove_server(server_id)
            self._json(200, {"removed": removed, "server_id": server_id})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_mcp_toggle(self, server_id: str, body: dict) -> None:
        if not _HAS_MCP_MANAGER:
            self._json(503, {"error": "MCP manager not available"})
            return
        server_id = server_id.strip().rstrip("/")
        enabled = bool(body.get("enabled", True))
        try:
            ok = _mcp_toggle_server(server_id, enabled)
            self._json(200, {"ok": ok, "server_id": server_id, "enabled": enabled})
        except Exception as exc:
            self._json(500, {"error": str(exc)})

    def _handle_test_connection(self, comp_id: str) -> None:
        comp_id = comp_id.strip().rstrip("/")
        if comp_id == "github":
            try:
                from tasks.github_client import GitHubClient
                from tasks.setup_config_store import get_component_values
                stored = get_component_values("github", include_secrets=True)
                kv = {item["config_key"]: item["config_value"] for item in stored}
                token = str(kv.get("GITHUB_TOKEN") or "").strip()
                if not token or token == "********":
                    token = os.getenv("GITHUB_TOKEN", "")
                client = GitHubClient(token=token)
                result = client.test_connection()
                self._json(200, result)
            except Exception as exc:
                self._json(200, {"ok": False, "error": str(exc)})
        else:
            self._json(200, {"ok": False, "error": f"No connection test available for '{comp_id}'."})


def main() -> None:
    apply_setup_env_defaults()
    host = os.getenv("KENDR_UI_HOST", _UI_HOST)
    port = int(os.getenv("KENDR_UI_PORT", str(_UI_PORT)))
    server = ThreadingHTTPServer((host, port), KendrUIHandler)
    _display_host = "localhost" if host in ("0.0.0.0", "") else host
    display_url = f"http://{_display_host}:{port}"
    print(f"Kendr UI running at {display_url}  (bound to {host}:{port})")
    print(f"  Chat:   {display_url}/")
    print(f"  Setup:  {display_url}/setup")
    print(f"  Runs:   {display_url}/runs")
    print(f"  MCP:    {display_url}/mcp")
    print(f"  Gateway: {_gateway_url()} ({'online' if _gateway_ready(timeout=0.5) else 'offline — run: kendr gateway start'})")
    server.serve_forever()


if __name__ == "__main__":
    main()
