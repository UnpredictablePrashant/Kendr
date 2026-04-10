# Capability Control Plane — Phase 5

Phase 5 hardens chat-time capability discoverability and prevents misrouting into communication-summary workflows.

## Delivered in Phase 5

1. Runtime discovery intent hardening:

- added `AgentRuntime._REGISTRY_DISCOVERY_RE`
- added `AgentRuntime._is_registry_discovery_request(state)`
- detects inventory-style prompts such as:
  - "what skills do you have"
  - "list capabilities"
  - "show available MCP servers/APIs/agents"

2. Deterministic capability-discovery shortcut:

- in `orchestrator_agent`, added a dedicated shortcut that returns `_skills_overview(...)` directly when registry discovery intent is detected.
- this path is independent of the conversational-call-count guard, so it still works after retries/noise.

3. Communication misroute prevention:

- updated `_is_communication_summary_request(...)` to return `False` for registry-discovery intents.
- avoids accidental routing to `communication_summary_agent` for capability listing prompts.

4. Better stuck-loop operator guidance:

- improved communication authorization guidance in `_stuck_agent_guidance(...)` with explicit alternatives:
  - ask for skills/capabilities in chat
  - use `kendr agents list`
  - call `GET /registry/skills` / `GET /registry/discovery/cards`

5. Test coverage:

- updated `tests/test_runtime_routing.py` with:
  - communication detector deconfliction test
  - post-guard-window capability discovery shortcut test
  - expanded stuck guidance assertion for discovery endpoint hints

## Validation

```bash
python3 -m unittest tests.test_runtime_routing tests.test_imports
```
