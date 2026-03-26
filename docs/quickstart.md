# Quickstart

This guide gets you from a fresh checkout to your first successful SuperAgent run.

## Prerequisites

- Python 3.10 or newer
- an `OPENAI_API_KEY`
- a working directory where SuperAgent can write run artifacts

Recommended for the best first experience:

- `SERP_API_KEY` for search-backed research workflows
- Docker if you want the full Qdrant and MCP stack

## 1. Install SuperAgent

Linux or macOS:

```bash
./scripts/install.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Manual install on any OS:

```bash
python3 -m pip install -e .
```

## 2. Configure Environment

Use `.env.example` as your baseline:

```bash
cp .env.example .env
```

Set at least:

- `OPENAI_API_KEY`
- `SERP_API_KEY` for search-heavy workflows

You can also inspect setup from the CLI:

```bash
superagent setup status
superagent setup components
```

If you prefer a local UI for OAuth-backed providers:

```bash
superagent setup ui
```

The setup UI runs on `http://127.0.0.1:8787` by default.

## 3. Choose A Working Directory

SuperAgent needs a working directory for artifacts and intermediate outputs.

Use the current folder:

```bash
superagent workdir here
```

Or pass it per run:

```bash
superagent run --current-folder "Create a short research brief on OpenAI."
```

## 4. Sanity Check

```bash
superagent --help
superagent agents list
superagent plugins list
superagent setup status
```

## 5. First Run

Use the actual CLI entrypoint:

```bash
superagent run --current-folder \
  "Create an intelligence brief on Stripe: business model, products, competitors, recent strategy moves, and top risks."
```

What to expect:

- the runtime ensures the gateway path is available
- the run may stop first on an approval-ready plan
- after approval, SuperAgent executes the workflow and writes artifacts under `output/runs/<run_id>/`

## 6. Recommended Next Runs

Local-drive intelligence:

```bash
superagent run \
  --drive="D:/xyz/folder" \
  "Review this folder, summarize the important files, and produce an executive-ready intelligence brief."
```

`superRAG` build:

```bash
superagent run \
  --superrag-mode build \
  --superrag-new-session \
  --superrag-session-title "product_ops_kb" \
  --superrag-path ./docs \
  --superrag-url https://example.com/help-center \
  "Create a reusable product operations knowledge session."
```

`superRAG` chat:

```bash
superagent run \
  --superrag-mode chat \
  --superrag-session product_ops_kb \
  --superrag-chat "What are the main operating risks and where are they sourced from?"
```

## Where To Go Next

- [Install](install.md) for the full setup surface
- [Examples](examples.md) for more workflows
- [Troubleshooting](troubleshooting.md) if the first run does not behave as expected
