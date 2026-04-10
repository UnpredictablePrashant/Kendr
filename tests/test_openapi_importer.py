import os
import tempfile
import unittest

from kendr.openapi_importer import import_openapi_as_capabilities, parse_openapi_payload
from kendr.persistence import get_capability_by_key, list_capabilities
from kendr.persistence.core import initialize_db


class OpenAPIImporterTests(unittest.TestCase):
    def test_parse_openapi_payload_json(self):
        parsed = parse_openapi_payload(spec_text='{"openapi":"3.0.0","info":{"title":"A"},"paths":{"/x":{"get":{"responses":{"200":{"description":"ok"}}}}}}')
        self.assertEqual(parsed["info"]["title"], "A")

    def test_import_openapi_creates_service_and_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "openapi.sqlite3")
            initialize_db(db_path)
            spec = {
                "openapi": "3.0.0",
                "info": {"title": "Billing API", "description": "Billing operations"},
                "paths": {
                    "/invoices": {
                        "get": {
                            "operationId": "listInvoices",
                            "summary": "List invoices",
                            "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"type": "array"}}}}},
                        }
                    },
                    "/invoices/{id}": {
                        "get": {
                            "summary": "Get invoice",
                            "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}],
                            "responses": {"200": {"description": "ok"}},
                        }
                    },
                },
            }
            result = import_openapi_as_capabilities(
                workspace_id="ws1",
                owner_user_id="u1",
                openapi_spec=spec,
                status="verified",
                db_path=db_path,
            )
            self.assertEqual(result["operations_synced"], 2)

            service = get_capability_by_key(workspace_id="ws1", key="api.service.billing_api", db_path=db_path)
            self.assertIsNotNone(service)
            self.assertEqual(service["type"], "api")
            self.assertEqual(service["status"], "verified")

            op1 = get_capability_by_key(workspace_id="ws1", key="api.operation.billing_api.get.listinvoices", db_path=db_path)
            self.assertIsNotNone(op1)
            self.assertEqual(op1["type"], "tool")
            self.assertEqual(op1["metadata"]["method"], "GET")

    def test_import_openapi_disables_stale_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "openapi_stale.sqlite3")
            initialize_db(db_path)

            spec_v1 = {
                "openapi": "3.0.0",
                "info": {"title": "Catalog API"},
                "paths": {
                    "/items": {
                        "get": {"operationId": "listItems", "responses": {"200": {"description": "ok"}}},
                    },
                    "/items/{id}": {
                        "get": {"operationId": "getItem", "responses": {"200": {"description": "ok"}}},
                    },
                },
            }
            import_openapi_as_capabilities(
                workspace_id="ws1",
                owner_user_id="u1",
                openapi_spec=spec_v1,
                db_path=db_path,
            )
            spec_v2 = {
                "openapi": "3.0.0",
                "info": {"title": "Catalog API"},
                "paths": {
                    "/items": {
                        "get": {"operationId": "listItems", "responses": {"200": {"description": "ok"}}},
                    },
                },
            }
            result = import_openapi_as_capabilities(
                workspace_id="ws1",
                owner_user_id="u1",
                openapi_spec=spec_v2,
                db_path=db_path,
            )
            self.assertGreaterEqual(result["stale_disabled"], 1)
            tools = list_capabilities(workspace_id="ws1", capability_type="tool", limit=100, db_path=db_path)
            stale = [t for t in tools if t["metadata"].get("operation_id") == "getItem"]
            self.assertTrue(stale)
            self.assertTrue(all(t["status"] == "disabled" for t in stale))


if __name__ == "__main__":
    unittest.main()

