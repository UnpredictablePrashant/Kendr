# Install

This guide covers local setup, environment configuration, Docker services, and verification commands.

## Runtime Requirements

- Python 3.10 or newer
- network access for configured APIs
- optional Docker for Qdrant and MCP services

## Environment Baseline

Start from `.env.example`.

Required for the main research stack:

- `OPENAI_API_KEY`
- `SERP_API_KEY`

Recommended:

- `OPENAI_MODEL`
- `OPENAI_VISION_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `RESEARCH_USER_AGENT`
- `SUPERAGENT_HOME`
- `SUPERAGENT_PLUGIN_PATHS`

Workflow-specific or optional:

- `ELEVENLABS_API_KEY`
- `GOOGLE_*`
- `SLACK_*`
- `MICROSOFT_*`
- `TELEGRAM_*`
- `WHATSAPP_*`
- `AWS_*`
- `NVD_API_KEY`

See [Integrations](integrations.md) for provider-specific details.

## Local Installation

### Linux Or macOS

```bash
./scripts/install.sh
```

This script:

- creates `.venv` if needed
- installs the package in editable mode
- bootstraps local runtime state
- adds `.venv/bin` to your shell path

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Preferred Chocolatey-assisted flow:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_choco.ps1
```

### Manual Install

```bash
python3 -m pip install -e .
```

## Setup Commands

Inspect setup:

```bash
superagent setup status
superagent setup components
```

Set values in the local setup store:

```bash
superagent setup set openai OPENAI_API_KEY sk-...
superagent setup set openai OPENAI_MODEL_GENERAL gpt-4.1-mini
```

Open the setup UI:

```bash
superagent setup ui
```

Export stored values as dotenv lines:

```bash
superagent setup export-env
superagent setup export-env --include-secrets
```

## Running Locally

Basic run:

```bash
superagent run --current-folder "Create a short research brief on OpenAI."
```

Gateway:

```bash
superagent gateway
```

Daemon:

```bash
superagent daemon
superagent daemon --once
```

Setup UI:

```bash
superagent setup ui
```

## Docker Stack

Start the Compose stack:

```bash
docker compose up --build
```

Compose currently includes:

- `qdrant`
- `app`
- `daemon`
- `gateway`
- `setup-ui`
- `research-mcp`
- `vector-mcp`
- `nmap-mcp`
- `zap-mcp`
- `screenshot-mcp`
- `http-fuzzing-mcp`
- `cve-mcp`

Docker is optional for local CLI use, but useful when you want the fuller Qdrant and MCP service stack.

## Verification Commands

Basic command checks:

```bash
superagent --help
superagent agents list
superagent plugins list
superagent setup status
```

Repository verification entrypoints:

```bash
python3 -m unittest discover -s tests -v
./scripts/ci_check.sh
```

If `make` is available on your machine, the repo also defines:

```bash
make compile
make test
make ci
```

## Uninstall

Linux or macOS:

```bash
./scripts/uninstall.sh
```

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall.ps1
```
