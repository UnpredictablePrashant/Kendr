# Capability Control Plane — Phase 6

Phase 6 adds governance and observability APIs for capability operations: health runs, audit trails, and policy profile management.

## Delivered in Phase 6

1. Persistence observability queries (`kendr/persistence/capability_store.py`):

- `list_capability_health_runs(...)`
- `list_capability_audit_events(...)`
- `list_auth_profiles(...)`
- `list_policy_profiles(...)`

2. Registry service extensions (`kendr/capability_registry.py`):

- health status validation (`unknown`, `healthy`, `degraded`, `down`)
- `record_health(...)` now audits health updates and returns updated capability
- list APIs:
  - `list_health_runs(...)`
  - `list_audit_events(...)`
  - `list_auth_profiles(...)`
  - `list_policy_profiles(...)`

3. Gateway governance + observability endpoints (`kendr/gateway_server.py`):

- `GET /registry/auth-profiles`
- `GET /registry/policy-profiles`
- `POST /registry/policy-profiles`
- `GET /registry/capabilities/{capability_id}/health`
- `GET /registry/capabilities/{capability_id}/audit`
- `POST /registry/capabilities/{capability_id}/health-check`

4. UI proxy + control-plane updates (`kendr/ui_server.py`):

- added UI proxies:
  - `GET /api/capabilities/auth-profiles`
  - `GET /api/capabilities/policy-profiles`
  - `POST /api/capabilities/policy-profiles`
  - `GET /api/capabilities/{capability_id}/health`
  - `GET /api/capabilities/{capability_id}/audit`
  - `POST /api/capabilities/{capability_id}/health-check`
- capability table actions now include:
  - health view
  - audit view
  - quick `Mark Healthy` action
- added policy profile creation form to the capabilities UI.

5. Test coverage:

- `tests/test_capability_store.py` validates new list helpers
- `tests/test_capability_registry_service.py` validates health/audit observability flow
- `tests/test_gateway_surface.py` validates policy profile + health/audit endpoints
- `tests/test_ui_server.py` validates UI proxy forwarding for health and policy routes

## Validation

```bash
python3 -m unittest \
  tests.test_capability_store \
  tests.test_capability_registry_service \
  tests.test_gateway_surface \
  tests.test_ui_server.TestUICapabilitiesSurface \
  tests.test_imports
```
