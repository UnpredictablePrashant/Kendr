# Capability Control Plane — Phase 2

Phase 2 adds API import and auth profile plumbing to the unified capability registry.

## Delivered in Phase 2

1. OpenAPI importer:

- `kendr/openapi_importer.py`
- parses JSON (and YAML when PyYAML is available)
- imports API service capability (`type=api`)
- imports operation capabilities (`type=tool`)
- links service -> operations via `exposes_tool`
- disables stale operations on re-import

2. Gateway endpoints:

- `POST /registry/auth-profiles`
  - creates auth profiles in unified registry
- `POST /registry/apis/import-openapi`
  - imports OpenAPI document into capabilities

3. Tests:

- `tests/test_openapi_importer.py`
- gateway endpoint coverage in `tests/test_gateway_surface.py`

## Validation

```bash
python3 -m unittest tests.test_openapi_importer tests.test_gateway_surface tests.test_imports
```

