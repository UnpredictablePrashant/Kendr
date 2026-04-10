# Capability Control Plane — Phase 0

Phase 0 establishes the persistence and service skeleton for a unified capability registry covering:

- skills
- MCP servers/tools
- APIs
- agents

It does not yet replace runtime routing or setup UI flows.

## Delivered in Phase 0

1. Schema extensions in SQLite (`initialize_db`):

- `capabilities`
- `capability_relations`
- `auth_profiles`
- `policy_profiles`
- `capability_health_runs`
- `capability_audit_events`

2. Persistence helpers:

- `kendr/persistence/capability_store.py`
- CRUD for capabilities
- relation linking
- auth/policy profile creation
- health run recording
- audit event insertion

3. Service wrapper:

- `kendr/capability_registry.py`
- publish/disable transitions
- audit-aware create/update/link operations

## Phase 0 Acceptance Checks

Run:

```bash
pytest -q tests/test_capability_store.py tests/test_capability_registry_service.py tests/test_imports.py
```

Expected:

- new schema tables are created without migration errors
- capability CRUD works against an isolated DB
- service wrapper can create/publish/link capabilities

## Next Phase Hooks

Phase 1 can wire MCP registration into this unified registry and expose first read APIs for chat discovery (`/registry/discovery`).

