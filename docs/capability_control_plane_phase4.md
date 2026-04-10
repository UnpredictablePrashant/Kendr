# Capability Control Plane — Phase 4

Phase 4 adds an operator UI for capability lifecycle and registry operations.

## Delivered in Phase 4

1. UI Control Plane page:

- added `GET /capabilities` in `kendr/ui_server.py`
- new `_CAPABILITIES_HTML` page for:
  - capability search/list/detail
  - lifecycle actions (`verify`, `publish`, `disable`)
  - create capability
  - create auth profile
  - import OpenAPI text
  - discovery card count visibility

2. UI to gateway API proxy surface:

- added UI API proxies in `kendr/ui_server.py`:
  - `GET /api/capabilities`
  - `GET /api/capabilities/{capability_id}`
  - `GET /api/capabilities/discovery`
  - `GET /api/capabilities/discovery/cards`
  - `POST /api/capabilities`
  - `POST /api/capabilities/{capability_id}/update`
  - `POST /api/capabilities/{capability_id}/verify`
  - `POST /api/capabilities/{capability_id}/publish`
  - `POST /api/capabilities/{capability_id}/disable`
  - `POST /api/capabilities/auth-profiles`
  - `POST /api/capabilities/import-openapi`

3. Unified gateway forward helper:

- added `_gateway_forward_json()` to normalize JSON proxying and HTTP error passthrough from UI -> gateway.

4. Navigation discoverability updates:

- added `Capabilities` nav entry to all major UI pages (`chat`, `setup`, `runs`, `rag`, `models`, `mcp`, `skills`, `projects`, `docs`).

5. Test coverage:

- added `TestUICapabilitiesSurface` in `tests/test_ui_server.py` covering:
  - capabilities page render
  - capabilities HTML action presence
  - GET proxy forwarding
  - lifecycle action proxy forwarding

## Validation

```bash
python3 -m unittest tests.test_ui_server
```
