# Capability Control Plane — Phase 3

Phase 3 adds capability CRUD and lifecycle workflow for skills and agents.

## Delivered in Phase 3

1. Capability lifecycle guardrails:

- implemented in `kendr/capability_registry.py`
- validates capability type/status/visibility
- enforces status transitions:
  - `draft -> verified -> active -> disabled/deprecated`
  - other guarded transitions with explicit validation errors

2. Gateway CRUD + workflow endpoints:

- `GET /registry/capabilities`
- `GET /registry/capabilities/{capability_id}`
- `POST /registry/capabilities`
- `POST /registry/capabilities/{capability_id}/update`
- `POST /registry/capabilities/{capability_id}/verify`
- `POST /registry/capabilities/{capability_id}/publish`
- `POST /registry/capabilities/{capability_id}/disable`

3. Test coverage:

- lifecycle and transition checks in `tests/test_capability_registry_service.py`
- gateway endpoint coverage in `tests/test_gateway_surface.py`

## Validation

```bash
python3 -m unittest tests.test_capability_registry_service tests.test_gateway_surface tests.test_imports
```

