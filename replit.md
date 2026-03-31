# Kendr Runtime

A plugin-driven multi-agent runtime and orchestration system built on LangGraph/LangChain.

## Architecture

- **`kendr/`** — Core package: runtime, registry, discovery, CLI, gateway server, setup UI
- **`tasks/`** — Built-in task agent modules (research, coding, security, file ops, etc.)
- **`mcp_servers/`** — MCP server implementations (research, vector, security)
- **`app.py`** — Entry point: builds registry and workflow
- **`setup_ui.py`** — Starts the web-based Setup Console
- **`gateway_server.py`** — Starts the HTTP gateway/dashboard server

## Running on Replit

The main workflow runs the **Kendr Setup Console** (web UI) on port 5000.

**Workflow command:**
```
SETUP_UI_HOST=0.0.0.0 SETUP_UI_PORT=5000 python3 setup_ui.py
```

## Key Environment Variables

Set via Replit secrets/env vars (see `.env.example` for the full list):

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Required for agent LLM calls |
| `SETUP_UI_HOST` | Bind host for Setup UI (set to `0.0.0.0`) |
| `SETUP_UI_PORT` | Port for Setup UI (set to `5000`) |
| `GATEWAY_HOST` | Bind host for Gateway server (set to `0.0.0.0`) |
| `GATEWAY_PORT` | Port for Gateway server (set to `8000`) |

## Python 3.10 Compatibility Fixes

The codebase was migrated from Python 3.11+ to 3.10 (Replit's default). Fixes applied:

1. **`datetime.UTC`** → replaced with `timezone.utc` across all task/kendr modules
2. **`typing.NotRequired`** → wrapped with try/except fallback to `typing_extensions` in `kendr/orchestration/state.py`

## Dependencies

Managed via `pyproject.toml`. Install with:
```
pip install -e ".[dev]"
```

Key dependencies: `langgraph`, `langchain`, `langchain-openai`, `openai`, `fastmcp`, `qdrant-client`, `playwright`, `boto3`, `telethon`

## Task #2: Deep Research & Document Generation Pipeline

New capabilities added:

### New functions in `tasks/research_infra.py`
- **`arxiv_search(query, max_results, sort_by)`** — Fetches academic papers from the arXiv Atom API (no API key required)
- **`reddit_search(query, subreddit, sort, limit)`** — Fetches Reddit posts from the public JSON search API (no auth required)

### New file: `tasks/research_pipeline_tasks.py`
- **`research_pipeline_agent(state)`** — Orchestrates multi-source evidence collection from any combination of: `web`, `arxiv`, `reddit`, `scholar`, `patents`, `openalex`
- Builds a combined markdown evidence report with formatted results per source
- Populates `long_document_evidence_bank_*` state keys when `long_document_collect_sources_first` is set

### CLI additions to `kendr/cli.py`
- **`--sources web,arxiv,reddit`** — Comma-separated source list for the research pipeline; sets `research_sources` in state
- **`--pages 50`** — Shorthand for `--long-document --long-document-pages 50`; implies long-form document mode

### State additions in `kendr/orchestration/state.py`
- `research_sources: list[str]`
- `research_pipeline_enabled: bool`

### MCP server updates in `mcp_servers/research_server.py`
- New `arxiv_papers` tool — fetches arXiv papers via MCP
- New `reddit_posts` tool — fetches Reddit posts via MCP

## Task #3: Multi-Agent Dev Project Generation

New `kendr generate` and `kendr research` subcommands added to `kendr/cli.py`.

### `kendr generate` command
Generates a complete multi-agent software project from a natural language description.

```
kendr generate "a FastAPI todo API with PostgreSQL" --auto-approve
kendr generate "a Next.js SaaS dashboard" --stack nextjs_prisma_postgres --name my-saas --output ~/projects
kendr generate "an Express REST API with MongoDB" --skip-tests --skip-devops
```

Flags:
- `description` — Natural language description of the project (positional)
- `--name NAME` — Project name in kebab-case; auto-derived if omitted
- `--stack STACK` — Stack template (fastapi_postgres, fastapi_react_postgres, nextjs_prisma_postgres, express_prisma_postgres, mern_microservices_mongodb, pern_postgres, nextjs_static_site)
- `--output PATH` — Output directory root (defaults to working directory)
- `--auto-approve` — Skip interactive blueprint/plan approval prompts
- `--skip-tests` — Omit test_agent from the build plan
- `--skip-devops` — Omit devops_agent (Dockerfile/CI/CD) from the build plan
- `--skip-reviews` — Skip reviewer agent between steps
- `--max-steps N` — Max orchestration steps (default 40)

Sets `project_build_mode=True` in state so the orchestrator directly routes to `project_blueprint_agent` without NLP detection.

### `kendr research` command
Runs a multi-source research pipeline and optionally generates a long-form document.

```
kendr research "transformer architectures 2024" --sources arxiv,openalex --pages 20
kendr research "AI in healthcare" --sources web,scholar,reddit --title "AI Healthcare Report"
kendr research "my local notes" --drive ~/documents --sources local
```

Flags:
- `query` — Research query or topic (positional)
- `--sources SOURCES` — Comma-separated sources (web, arxiv, reddit, scholar, patents, openalex, local)
- `--pages N` — Target page count; implies long-form document mode
- `--title TITLE` — Optional document title
- `--drive PATH` — Local folder/file path (repeatable)
- `--research-model MODEL` — Override deep-research model
- `--auto-approve` — Auto-approve plan gates

### New file: `tasks/dev_pipeline_tasks.py`
- `dev_pipeline_agent(state)` — end-to-end synchronous pipeline orchestrator
- Stages: blueprint → blueprint approval gate → scaffold → db → auth → backend → frontend → deps → tests → security scan → devops → verify → auto-fix loop → post-setup → zip export
- **Blueprint approval gate**: Interactive y/n prompt (skipped when `auto_approve=True`)
- **Auto-fix retry loop**: Up to `dev_pipeline_max_fix_rounds` (default 3) rounds — invokes `coding_agent` to fix when `project_verifier_agent` fails
- **Zip export**: Packages generated project into `<project_name>.zip` in parent of `project_root`; writes path to `dev_pipeline_zip_path` state key
- `dev_pipeline_zip_path` persisted to `dev_pipeline_zip_path.txt` in the output directory

### `kendr run --dev` flag
- `--dev` — activates `dev_pipeline_mode`, routes to `dev_pipeline_agent` instead of planner
- `--dev-skip-tests` — omit test stage
- `--dev-skip-devops` — omit devops stage
- `--dev-max-fix-rounds N` — override auto-fix retry count (default 3)

### Runtime changes
- `_is_project_build_request()` in `kendr/runtime.py` — now returns `True` immediately when `project_build_mode` is already set in state (avoids requiring NLP marker detection for `generate` command)
- New routing block in `kendr/runtime.py` — routes to `dev_pipeline_agent` when `dev_pipeline_mode=True`; takes priority over individual `project_blueprint_agent` routing
- `skip_test_agent: bool` and `skip_devops_agent: bool` added to `RuntimeState` in `kendr/orchestration/state.py`
- New dev pipeline state keys: `dev_pipeline_mode`, `dev_pipeline_status`, `dev_pipeline_stages_completed`, `dev_pipeline_error`, `dev_pipeline_zip_path`, `dev_pipeline_max_fix_rounds`, `project_verifier_status`, `project_verifier_output`
- Planner prompt updated to honor `skip_test_agent` and `skip_devops_agent` flags from planning context
