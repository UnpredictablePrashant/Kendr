# Integrations

Kendr routes against configured integrations, not against the full theoretical ecosystem. If an integration is missing or disabled, setup-aware routing removes dependent agents from `available_agents`.

The integration lifecycle is standardized across:

- declaration in [`kendr/setup/catalog.py`](../kendr/setup/catalog.py)
- configuration via `kendr setup ...` and [`.env.example`](../.env.example)
- setup detection and health reporting in [`tasks/setup_registry.py`](../tasks/setup_registry.py)
- routing eligibility through agent `requirements`
- docs and tests

Future integrations should follow [Integration Checklist](integration_checklist.md).

---

## Lifecycle

| Stage | Source Of Truth |
| --- | --- |
| declaration | `kendr/setup/catalog.py` |
| configuration fields | `tasks/setup_config_store.py` via the shared catalog |
| health/detection | `tasks/setup_registry.py` |
| routing eligibility | `AGENT_METADATA["requirements"]` |
| concrete setup examples | `.env.example`, `README.md`, `SampleTasks.md` |
| regression coverage | `tests/test_setup_registry.py` and related routing tests |

---

## Built-In Providers

| Provider | Purpose | Key Variables |
| --- | --- | --- |
| `openai` | Orchestration, reasoning, OCR, embeddings, deep research | `OPENAI_API_KEY`, `OPENAI_MODEL_GENERAL`, `OPENAI_MODEL_CODING` |
| `serpapi` | Web, travel, scholarly, and patent search | `SERP_API_KEY` |
| `elevenlabs` | Speech synthesis and transcription | `ELEVENLABS_API_KEY` |
| `google_workspace` | Gmail and Google Drive | `GOOGLE_ACCESS_TOKEN` or OAuth client fields |
| `microsoft_graph` | Outlook, Teams, OneDrive | `MICROSOFT_GRAPH_ACCESS_TOKEN` or OAuth client fields |
| `slack` | Slack workspace bot | `SLACK_BOT_TOKEN` or OAuth client fields |
| `telegram` | Telegram bot or user-session | `TELEGRAM_BOT_TOKEN` or `TELEGRAM_SESSION_STRING` + API fields |
| `whatsapp` | WhatsApp Cloud API (Meta) | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` |
| `aws` | AWS cloud workflows | `AWS_*` environment variables |
| `qdrant` | Vector memory (opt-in) | `QDRANT_URL`, `QDRANT_COLLECTION` |
| `playwright` | Browser automation and screenshots | Playwright package or CLI |
| `nmap` | Authorized host scanning | Local `nmap` binary |
| `zap` | OWASP ZAP baseline scanning | `zap-baseline.py` or `owasp-zap` on PATH |
| `cve_database` | CVE and NVD lookup | `CVE_API_BASE_URL`, optional `NVD_API_KEY` |

---

## Built-In Channels

| Channel | Status |
| --- | --- |
| `webchat` | Available via gateway |
| `telegram` | Stable |
| `slack` | Stable |
| `whatsapp` | Beta |
| `teams` | Beta |
| `discord` | Registered (connector pending) |
| `matrix` | Registered (connector pending) |
| `signal` | Registered (connector pending) |

---

## Vector Backend: ChromaDB vs Qdrant

### ChromaDB (default — zero setup required)

ChromaDB is the default vector backend. It runs in-process with no configuration, no external service, and no environment variables required. It is selected automatically when `QDRANT_URL` is not set or Qdrant is unreachable.

ChromaDB is suitable for:
- Single-user local deployments
- Getting started quickly
- Runs where persistence is local and not shared across machines

Data is stored under `KENDR_WORKING_DIR/.chroma/` by default.

### Qdrant (opt-in — persistent, scalable)

To use Qdrant, set `QDRANT_URL` to a reachable Qdrant endpoint. Kendr performs a health check before using Qdrant; if the endpoint is unreachable, it falls back to ChromaDB.

```bash
# .env
QDRANT_URL="http://127.0.0.1:6333"
QDRANT_API_KEY=""                    # optional, for authenticated Qdrant
QDRANT_COLLECTION="research_memory"  # default collection name
```

Start Qdrant with Docker:

```bash
docker run -p 6333:6333 qdrant/qdrant
```

Or via the included Compose stack:

```bash
docker compose up qdrant
```

Qdrant is suitable for:
- Team or multi-user deployments
- Persistent superRAG knowledge sessions shared across machines
- High-volume vector indexing

---

## Specific Integrations

### OpenAI

Required for the core runtime. All agents depend on `openai` or the local `codex_cli` alternative.

```bash
kendr setup set openai OPENAI_API_KEY sk-...
kendr setup set openai OPENAI_MODEL_GENERAL gpt-4o
```

The minimum concrete setup is just `OPENAI_API_KEY`. The model defaults to `gpt-4o-mini`.

### SerpAPI

Required for structured web search, travel, patent, and scholarly search.

```bash
kendr setup set serpapi SERP_API_KEY your-serp-api-key
```

Get your key at [serpapi.com](https://serpapi.com). Without this, search-backed agents are filtered from routing.

### Google Workspace

Configure **either** a direct access token **or** OAuth client credentials.

**Direct token (quick start):**

```bash
GOOGLE_ACCESS_TOKEN="ya29.a0..."
```

**OAuth flow (recommended for longevity):**

```bash
GOOGLE_CLIENT_ID="123456-abc.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="GOCSPX-..."
GOOGLE_REDIRECT_URI="http://127.0.0.1:8787/oauth/google/callback"
```

Then complete the OAuth flow:

```bash
kendr setup ui         # opens http://127.0.0.1:8787
# OR
kendr setup oauth google
```

If client credentials exist but no token has been acquired, setup reports the integration as OAuth-ready but not configured.

### Microsoft Graph (Outlook + Teams + OneDrive)

Configure **either** a direct access token **or** OAuth client credentials.

**Direct token:**

```bash
MICROSOFT_GRAPH_ACCESS_TOKEN="eyJ0eXAi..."
```

**OAuth flow:**

```bash
MICROSOFT_CLIENT_ID="11112222-3333-4444-5555-666677778888"
MICROSOFT_CLIENT_SECRET="aBcDeFgHiJkL..."
MICROSOFT_TENANT_ID="common"          # or your specific tenant ID
MICROSOFT_REDIRECT_URI="http://127.0.0.1:8787/oauth/microsoft/callback"
```

Then run:

```bash
kendr setup oauth microsoft
```

OneDrive, Outlook, and Teams agents stay disabled until a usable token exists.

### Slack

Configure **either** a bot token **or** OAuth app credentials.

**Bot token (quick start):**

```bash
SLACK_BOT_TOKEN="xoxb-..."
```

**OAuth app:**

```bash
SLACK_CLIENT_ID="123456789012.1234567890"
SLACK_CLIENT_SECRET="abc123..."
```

Then install the app:

```bash
kendr setup oauth slack
```

### Telegram

Telegram supports two modes:

**Bot mode** — easier setup, requires the bot to be a member of the target channel/group:

```bash
TELEGRAM_BOT_TOKEN="1234567890:ABCDEFghijklmnop..."
```

Get your bot token from [@BotFather](https://t.me/BotFather) on Telegram.

**User-session mode** — uses your personal account via Telethon; can read any channel/group you have access to:

```bash
TELEGRAM_API_ID="12345678"
TELEGRAM_API_HASH="abcdef1234567890abcdef1234567890"
TELEGRAM_SESSION_STRING="..."         # generated once, see below
```

To get `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`: log in at [my.telegram.org](https://my.telegram.org/apps) and create an application.

To generate a `TELEGRAM_SESSION_STRING` (run once):

```bash
pip install telethon
python3 -c "
from telethon.sync import TelegramClient
import os
c = TelegramClient('session', int(os.environ['TELEGRAM_API_ID']), os.environ['TELEGRAM_API_HASH'])
c.start()
print(c.session.save())
"
```

Copy the printed string into `TELEGRAM_SESSION_STRING`.

### WhatsApp

Kendr integrates with the **Meta WhatsApp Cloud API**. You need a Meta Business account and a registered WhatsApp Business phone number.

```bash
WHATSAPP_ACCESS_TOKEN="EAAGm0PX4ZC..."       # Meta Graph API access token
WHATSAPP_PHONE_NUMBER_ID="109876543210"      # phone number ID (NOT the number itself)
```

**Where to get these:**

1. Go to [developers.facebook.com](https://developers.facebook.com/apps) and create an app.
2. Add the **WhatsApp** product to your app.
3. In WhatsApp > API Setup, find your Phone Number ID.
4. Generate a permanent token in System Users under Business Settings.

**Send a WhatsApp message:**

```bash
kendr run \
  --whatsapp-to "+15551234567" \
  --whatsapp-message "Hello from Kendr." \
  "Send a WhatsApp message."
```

**Use a message template:**

```bash
kendr run \
  --whatsapp-to "+15551234567" \
  --whatsapp-template "hello_world" \
  "Send a WhatsApp template message."
```

### GitHub

Enables `github_agent` to autonomously operate on GitHub repositories from a
natural language task description.

**Required env:** `GITHUB_TOKEN`

```bash
kendr setup set github GITHUB_TOKEN ghp_...
```

**Supported operations:** clone repo, pull, create/switch branch, read/write file,
commit, push, diff, list/get issues, add comment, create PR, merge PR.

**Token scopes required:**
- Public repos: `public_repo`
- Private repos: `repo`
- PR merge with workflow changes: `repo` + `workflow`

**Security model:**
The PAT is never embedded in the git remote URL. Authentication is injected via
`http.extraHeader` through git's `GIT_CONFIG_COUNT / GIT_CONFIG_KEY_* / GIT_CONFIG_VALUE_*`
environment variables — not visible in `ps aux` or stored in `.git/config`.
All file read/write ops enforce path-traversal protection.

**Example task:**

```bash
kendr run "Fix the failing test in acme-corp/my-service and open a PR with the fix."
```

**Test the connection:**
```bash
kendr setup show github
# Or from the Setup UI: open the GitHub card → Test connection
```

---

### AWS

AWS credentials are resolved through the standard boto3 credential chain: env vars, `~/.aws/credentials` profile, or instance role. No configuration is strictly required if an instance profile is active.

Explicit static credentials:

```bash
AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/..."
AWS_DEFAULT_REGION="us-east-1"
```

### Security Tools

`nmap`, `zap`, and `dependency-check` are local binary dependencies, not remote APIs. Security agents stay hidden when their required tools are missing.

Install them:

```bash
kendr setup install --yes
```

Or install manually:

```bash
# Ubuntu / Debian
sudo apt-get install nmap

# macOS
brew install nmap

# OWASP ZAP (all platforms)
# Download from https://www.zaproxy.org/download/
```

The CVE database uses the public NVD API endpoint by default. Set `NVD_API_KEY` for higher rate limits:

```bash
NVD_API_KEY="nvd-api-key-here"
```

---

### ElevenLabs

Required for voice synthesis and transcription workflows.

```bash
ELEVENLABS_API_KEY="el_sk_..."
```

Get your key at [elevenlabs.io](https://elevenlabs.io). Without this, voice and audio agents are disabled.

### Qdrant

See the [Vector Backend section above](#vector-backend-chromadb-vs-qdrant) for the full Qdrant setup guide. The key environment variables are:

```bash
QDRANT_URL="http://127.0.0.1:6333"
QDRANT_API_KEY=""
QDRANT_COLLECTION="research_memory"
```

### Playwright

Required for browser automation and screenshot workflows.

```bash
pip install playwright
playwright install chromium
```

Or use the install command:

```bash
kendr setup install --yes --only playwright
```

### CVE Database

Provides CVE and NVD vulnerability lookup capabilities. Uses the public NVD API by default — no setup required. Optionally add an NVD API key for higher rate limits.

```bash
CVE_API_BASE_URL="https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_API_KEY=""     # optional — raises rate limits
```

### Coding Integrations

Kendr coding agents work via OpenAI (`OPENAI_API_KEY`) by default. Optionally, the local `codex` CLI can be used as a fallback:

```bash
# install the codex CLI via npm
npm install -g @openai/codex

# Set the preferred coding backend
OPENAI_MODEL_CODING="gpt-4o"
OPENAI_CODEX_MODEL=""      # legacy fallback after OPENAI_MODEL_CODING
```

The `coding_backend` can also be specified per-run with `kendr run --coding-backend codex-cli`.

### Privileged Control

Controls safety boundaries for local command execution and OS automation. All gates are disabled by default.

```bash
KENDR_PRIVILEGED_MODE="false"       # enable privileged policy controls
KENDR_REQUIRE_APPROVALS="true"      # require --privileged-approved flag
KENDR_READ_ONLY_MODE="false"        # block all mutating commands
KENDR_ALLOW_ROOT="false"            # allow sudo/root escalation
KENDR_ALLOW_DESTRUCTIVE="false"     # allow destructive operations
KENDR_ENABLE_BACKUPS="true"         # snapshot before mutating actions
KENDR_ALLOWED_PATHS=""              # comma-separated allowed path roots
KENDR_ALLOWED_DOMAINS=""            # comma-separated allowed domains
KENDR_KILL_SWITCH_FILE="output/KENDR_STOP"
```

Each privileged run must include `--privileged-approved` and `--privileged-approval-note` with a ticket reference.

---

## Setup UI and OAuth

The CLI exposes a local web UI for OAuth-backed flows:

```bash
kendr setup ui
```

The setup UI runs at `http://127.0.0.1:8787` by default. It supports OAuth flows for Google, Microsoft, and Slack.

Useful setup commands:

```bash
kendr setup status                          # show all integration health
kendr setup components                      # list all configurable components
kendr setup show openai --json              # show one component
kendr setup export-env                      # export config as dotenv lines
kendr setup install --yes                   # install local tools
```

---

## Health and Routing

`build_setup_snapshot()` reports each integration with:

- `configured` — required variables are present
- `enabled` — not manually disabled
- `status` — health check result
- `health.detail` — human-readable health explanation
- `setup_hint` — what to do if not configured
- `docs_path` — link to docs section

Routing uses those results to populate `available_agents`, `disabled_agents`, and `setup_actions`. An agent that depends on an unconfigured integration is never routed to.

---

## Plugin Discovery

External plugins are loaded from:

- `./plugins`
- `~/.kendr/plugins`
- any path listed in `KENDR_PLUGIN_PATHS`

Plugin files are simple Python modules that expose `register(registry)`.

Example templates:

- [`plugin_templates/echo_plugin.py`](../plugin_templates/echo_plugin.py)
- [`plugin_templates/provider_plugin.py`](../plugin_templates/provider_plugin.py)

See [Plugin SDK](plugin_sdk.md) for manifest expectations, compatibility notes, and testing guidance.

### One-Stop Extensibility (Custom Skills + MCP)

Use this flow when you want any user to add their own skills and MCP servers:

1. Create/register custom skill agents as plugins (`register(registry)` + `AgentDefinition` metadata).
2. Add one or more MCP servers:

```bash
kendr mcp add "Server A" http://localhost:8000/mcp
kendr mcp add "Server B" "python mcp_servers/my_server.py" --type stdio
kendr mcp discover "Server A"
kendr mcp discover "Server B"
```

3. Verify discoverability surfaces used by runtime/chat routing:

```bash
kendr agents list
kendr mcp list
curl http://127.0.0.1:8790/registry/skills
```

The gateway re-registers discovered MCP tools as synthetic `mcp_*_agent` entries, and the skill registry includes them in routing once enabled/configured.

---

## MCP Servers

| Service | Purpose | Entry Script |
| --- | --- | --- |
| Research MCP | Web search, crawl, document parsing, OCR, entity brief | [`mcp_servers/research_server.py`](../mcp_servers/research_server.py) |
| Vector MCP | Text indexing and semantic search | [`mcp_servers/vector_server.py`](../mcp_servers/vector_server.py) |
| Nmap MCP | Safe host discovery and service scans | [`mcp_servers/nmap_server.py`](../mcp_servers/nmap_server.py) |
| ZAP MCP | Baseline web scan summaries | [`mcp_servers/zap_server.py`](../mcp_servers/zap_server.py) |
| Screenshot MCP | Browser screenshots and scripted capture | [`mcp_servers/screenshot_server.py`](../mcp_servers/screenshot_server.py) |
| HTTP Surface MCP | Safe HTTP surface probing | [`mcp_servers/http_fuzzing_server.py`](../mcp_servers/http_fuzzing_server.py) |
| CVE MCP | CVE and OSV lookup | [`mcp_servers/cve_server.py`](../mcp_servers/cve_server.py) |

---

## Dockerized Service Surface

The Compose stack includes:

- `qdrant` — vector store
- `app` — main Kendr runtime
- `daemon` — monitor and heartbeat
- `gateway` — HTTP gateway server
- `setup-ui` — OAuth and setup UI
- all current MCP services

```bash
docker compose up --build
```

See [Install](install.md) for the full Docker path.
