# Integrations

SuperAgent routes against real setup, not just against the full theoretical ecosystem.

If an integration is missing or disabled, setup-aware routing filters the dependent agents out of the available runtime card list.

## Built-In Providers

These providers are registered by the discovery layer today.

| Provider | Purpose | Typical Configuration |
| --- | --- | --- |
| `openai` | orchestration, reasoning, OCR, embeddings, deep research | `OPENAI_API_KEY`, model env vars |
| `elevenlabs` | speech and voice workflows | `ELEVENLABS_API_KEY` |
| `serpapi` | web, travel, scholarly, and patent search | `SERP_API_KEY` |
| `google_workspace` | Gmail and Google Drive | `GOOGLE_*` |
| `telegram` | Telegram bot or session access | `TELEGRAM_*` |
| `slack` | Slack workspace access | `SLACK_*` |
| `microsoft_graph` | Outlook, Teams, OneDrive | `MICROSOFT_*` |
| `aws` | AWS cloud workflows | `AWS_*` |
| `qdrant` | vector memory | `QDRANT_URL`, `QDRANT_COLLECTION` |
| `whatsapp` | WhatsApp Cloud API | `WHATSAPP_*` |
| `playwright` | browser automation and screenshots | Python package plus browser install |
| `nmap` | local network scanning | local `nmap` binary |
| `zap` | OWASP ZAP baseline scanning | local `zap-baseline.py` |
| `cve_database` | CVE and NVD lookup | optional `NVD_API_KEY` |

## Built-In Channels

The runtime currently registers these channels:

- `webchat`
- `telegram`
- `slack`
- `whatsapp`
- `teams`
- `discord`
- `matrix`
- `signal`

## Setup UI And OAuth

The CLI exposes a web-based setup UI:

```bash
superagent setup ui
```

OAuth-backed flows currently documented in the repo:

- Google Workspace
- Microsoft Graph
- Slack

Manual or direct-token integrations:

- Telegram bot token or Telethon session
- WhatsApp Cloud API
- AWS credentials

Useful setup commands:

```bash
superagent setup status
superagent setup components
superagent setup show openai --json
superagent setup export-env
superagent setup install --yes
```

## Plugin Discovery

External plugins are loaded from:

- `./plugins`
- `~/.superagent/plugins`
- any path listed in `SUPERAGENT_PLUGIN_PATHS`

Plugin files are simple Python modules that expose `register(registry)`.

Example:

- [`plugin_templates/echo_plugin.py`](../plugin_templates/echo_plugin.py)

## MCP Servers

The repo includes these MCP surfaces:

| Service | Purpose | Entry Script |
| --- | --- | --- |
| Research MCP | web search, crawl, document parsing, OCR, entity brief | [`mcp_servers/research_server.py`](../mcp_servers/research_server.py) |
| Vector MCP | text indexing and semantic search | [`mcp_servers/vector_server.py`](../mcp_servers/vector_server.py) |
| Nmap MCP | safe host discovery and service scans | [`mcp_servers/nmap_server.py`](../mcp_servers/nmap_server.py) |
| ZAP MCP | baseline web scan summaries | [`mcp_servers/zap_server.py`](../mcp_servers/zap_server.py) |
| Screenshot MCP | browser screenshots and scripted capture | [`mcp_servers/screenshot_server.py`](../mcp_servers/screenshot_server.py) |
| HTTP Surface MCP | safe HTTP surface probing | [`mcp_servers/http_fuzzing_server.py`](../mcp_servers/http_fuzzing_server.py) |
| CVE MCP | CVE and OSV lookup | [`mcp_servers/cve_server.py`](../mcp_servers/cve_server.py) |

## Dockerized Service Surface

The Compose stack currently includes:

- `qdrant`
- `app`
- `daemon`
- `gateway`
- `setup-ui`
- all current MCP services

See [Install](install.md) for the `docker compose up --build` path.
