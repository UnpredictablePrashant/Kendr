# Capability Control Plane — Phase 1

Phase 1 wires MCP flow into the unified capability registry and introduces read endpoints for chat/UI discovery.

## Delivered in Phase 1

1. MCP sync module:

- `kendr/capability_sync.py`
- mirrors MCP servers as `mcp_server` capabilities
- mirrors discovered MCP tools as `tool` capabilities
- creates `exposes_tool` relations
- disables stale synced MCP capabilities

2. MCP lifecycle integration:

- `kendr/mcp_manager.py` now triggers sync after add/remove/toggle/discover
- `kendr/discovery.py` triggers sync before synthetic MCP agent registration

3. Discovery APIs in gateway:

- `GET /registry/discovery?workspace_id=<id>`
- `GET /registry/discovery/cards?workspace_id=<id>`

Both endpoints include unified capability data (with MCP-backed capabilities after sync).

## Validation

Run:

```bash
python3 -m unittest tests.test_capability_sync tests.test_gateway_surface tests.test_imports
```

