# Platform Refactor Plan

This document turns the architecture review into an executable migration plan.

## What Changes First

The first objective is not feature breadth. It is reducing ambiguity and startup fragility in the platform kernel.

Phase 0 focuses on:

- making runtime plugin discovery explicit and resilient
- separating runtime plugin concepts from service integrations in the docs and contracts
- introducing a migration seam for strict versus best-effort registry discovery

## Canonical Object Model

These should become the first-class product objects over time:

- `integration`: a configured connection to an external system such as GitHub, Slack, Gmail, or a local service
- `runtime_plugin`: a packaged code extension that registers agents, providers, channels, or workflows with the runtime
- `mcp_server`: a configured MCP endpoint or stdio process
- `tool`: a typed callable operation
- `skill`: a reusable composition that wraps prompts, tools, or code behind a typed contract
- `agent`: a decision-making runtime node with model policy and allowed skills/tools
- `workflow`: a durable graph with checkpoints, retries, cancellation, and run metadata
- `model_endpoint`: a local or hosted inference target with capability and resource metadata
- `memory_store`: a scoped persistence surface for session memory, user memory, artifacts, or retrieval indexes

Objects that should not stay first-class in the end-user UX:

- raw provider SDK details
- internal routing metadata
- storage backend implementation details
- synthetic agent wrappers used only for compatibility

## Target Package Boundaries

The codebase should converge toward these package responsibilities:

- `kendr/control_plane`
  Installation, config, permissions, marketplace metadata, extension lifecycle.
- `kendr/runtime_kernel`
  Workflow execution, routing, cancellation, checkpointing, and policy evaluation.
- `kendr/extensions`
  Runtime plugin manifest, discovery, loading, compatibility checks, and isolation contracts.
- `kendr/extension_host`
  Separate subprocess host for unsafe tools, MCP transports, and custom code execution.
- `kendr/data`
  Metadata persistence, artifacts, memory indexes, and cache ownership.
- `kendr/observability`
  Traces, prompt snapshots, tool I/O redaction, replay, and profiling hooks.

## Migration Phases

### Phase 0: Stabilize Discovery

- add strict and best-effort discovery modes
- record discovery failures explicitly instead of failing silently
- remove eager provider imports from module import paths
- clarify that runtime plugins are not the same object as service integrations

### Phase 1: Split The Extension Surface

- replace overloaded “plugin” naming in the UX and docs with `integration` for external services
- keep `runtime_plugin` as the packaged code extension term
- move service integration cards out of `plugin_manager` naming over a compatibility window
- introduce permission manifests for runtime plugins and MCP-backed tools

### Phase 2: Isolate Execution

- move custom skill code execution out of process
- execute MCP stdio servers under a killable subprocess host with resource limits
- add per-extension permission prompts, audit events, and kill switches

### Phase 3: Separate Control And Execution Planes

- stop instantiating the full runtime at import time
- create an explicit control-plane bootstrap that can inspect extensions without starting the execution kernel
- give the UI a stable API boundary instead of importing large runtime modules directly

### Phase 4: Typed Workflows And Memory Scopes

- replace the large shared runtime state map with typed state slices
- make session memory, user memory, retrieval memory, and artifacts separate stores with explicit ownership
- move from synthetic-agent compatibility wrappers toward typed tools and workflows

## Proposed V1 Runtime Plugin Manifest

The current Python-module plugin contract can stay for compatibility, but the next manifest should describe a runtime plugin explicitly.

```python
PLUGIN = {
    "name": "acme.example",
    "description": "Example Kendr runtime plugin.",
    "version": "0.1.0",
    "plugin_type": "runtime_plugin",
    "sdk_version": "1.0",
    "runtime_api": "registry-v1",
    "entry_point": "register",
    "capabilities": ["agent", "provider"],
    "metadata": {
        "compatible_core": ">=0.2.0",
        "permissions": [
            "secrets:EXAMPLE_API_KEY",
            "network:api.example.com",
        ],
        "isolation": {
            "mode": "in_process",
            "notes": "Phase 2 should move unsafe code to a subprocess host.",
        },
    },
}
```

Fields to keep stable:

- `name`
- `version`
- `plugin_type`
- `sdk_version`
- `runtime_api`
- `entry_point`
- `capabilities`

Fields that can evolve behind metadata first:

- permission requirements
- isolation mode
- compatibility ranges
- extension health contracts

## What To Build Next

The next code slices should be:

1. move integration-card terminology out of `plugin_manager` into an `integration` surface
2. stop storing secrets and provider tokens as plain text in the same general SQLite store
3. introduce an extension host process for shell/code/MCP isolation
4. split control-plane bootstrap from runtime bootstrap
