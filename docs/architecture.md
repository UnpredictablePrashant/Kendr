# Architecture

SuperAgent is built as a setup-aware multi-agent runtime with dynamic discovery, gated routing, durable artifacts, and reusable memory.

## Runtime Flow

At a high level, a run goes through these stages:

1. receive a user query from the CLI or gateway
2. load the runtime registry of agents, providers, channels, and plugins
3. detect which integrations and local tools are actually configured
4. filter the available agent set to only eligible capabilities
5. plan the work
6. route to the next agent through the orchestrator
7. persist messages, tasks, artifacts, and outputs
8. stop when the answer is good enough or `max_steps` is reached

## Key Modules

- [`superagent/runtime.py`](../superagent/runtime.py)
  Dynamic orchestration runtime and routing loop.
- [`superagent/orchestration/state.py`](../superagent/orchestration/state.py)
  Shared runtime-state typing and pause/resume state helpers.
- [`superagent/discovery.py`](../superagent/discovery.py)
  Discovery of built-in agents, external plugins, providers, and channels.
- [`superagent/registry.py`](../superagent/registry.py)
  Runtime registry for agents, providers, channels, and plugins.
- [`superagent/cli.py`](../superagent/cli.py)
  Main command surface.
- [`superagent/gateway_server.py`](../superagent/gateway_server.py)
  Lightweight HTTP gateway and dashboard surface.
- [`superagent/http/`](../superagent/http/)
  HTTP-facing session-key and resume helpers shared by CLI and gateway surfaces.
- [`superagent/setup/`](../superagent/setup/)
  Setup-aware integration detection surface used by runtime and setup UI.
- [`superagent/setup/catalog.py`](../superagent/setup/catalog.py)
  Canonical integration declaration source for setup fields, discovery metadata, docs links, and routing contracts.
- [`superagent/providers/`](../superagent/providers/)
  Provider and OAuth access helpers used by communication and ingestion agents.
- [`superagent/domain/`](../superagent/domain/)
  Shared domain workflow logic extracted from large agent modules by responsibility.
- [`tasks/a2a_protocol.py`](../tasks/a2a_protocol.py)
  Internal task/message/artifact protocol.
- [`superagent/persistence/`](../superagent/persistence/)
  Durable SQLite persistence split by runtime, setup, and superRAG responsibilities.
- [`tasks/sqlite_store.py`](../tasks/sqlite_store.py)
  Backward-compatible import shim for the legacy persistence path.
- [`tasks/research_infra.py`](../tasks/research_infra.py)
  Shared research helpers, document parsing, OCR, chunking, and vector support.

## Discovery And Plugin Model

The registry layer does four things:

- discovers built-in agents by scanning task modules for `*_agent` functions
- reads `AGENT_METADATA` when present for richer agent cards
- discovers external plugins from plugin search paths
- exposes providers, channels, plugins, and agents through one runtime registry

Default external plugin search paths:

- `./plugins`
- `~/.superagent/plugins`
- additional paths in `SUPERAGENT_PLUGIN_PATHS`

External plugins are simple Python modules that expose `register(registry)`.

See [Plugin SDK](plugin_sdk.md) for the versioned external contract and what is stable versus internal.

## Setup-Aware Routing

SuperAgent does not route against the full theoretical surface by default.

`superagent/setup` and `tasks/setup_registry.py` detect:

- configured API providers
- installed local tools
- OAuth-backed services
- service reachability where relevant

The runtime then filters the available agent set so unconfigured surfaces are not selected.

## Planning And A2A Flow

Agents communicate through an internal A2A-inspired structure:

- tasks
- messages
- artifacts
- agent cards

Planning is a first-class stage:

- new work is planned before execution
- plans are stored in session memory and run artifacts
- the run can pause for approval before continuing
- long-document workflows add a second approval stage for section planning

## Persistence And Outputs

SuperAgent stores durable state in SQLite, including:

- runs
- agent cards
- tasks
- messages
- artifacts
- agent executions

Each run also writes artifacts under `output/runs/<run_id>/`, including:

- `execution.log`
- `final_output.txt`
- agent `.txt` and `.json` artifacts
- generated files such as `.html`, `.pdf`, and `.xlsx` outputs when applicable

## Memory And Retrieval

Vector memory is backed by Qdrant plus OpenAI embeddings.

The current memory layer supports:

- chunking web, document, and OCR text
- embedding text
- upserting memory records
- semantic retrieval for downstream agents

This is the foundation for `superRAG`, local-drive reuse, and cross-document synthesis.

## Services

SuperAgent currently supports these service shapes:

- CLI runtime
- HTTP gateway
- setup UI
- daemon loop for monitoring and heartbeats
- Dockerized Qdrant
- MCP servers for research, vector search, screenshots, Nmap, ZAP, HTTP probing, and CVE lookup

See [Install](install.md) and [Integrations](integrations.md) for the operational surface.

## Supporting Docs

- [Core Intelligence Stack](super_agent_stack.md)
- [superRAG](superrag_feature.md)
- [Local Drive Case Study](local_drive_case_study.md)
