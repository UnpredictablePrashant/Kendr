import os
import tempfile
import unittest

from kendr.capability_sync import sync_mcp_capabilities
from kendr.persistence import get_capability_by_key, list_capabilities
from kendr.persistence.core import initialize_db
from kendr.persistence.mcp_store import add_mcp_server, update_mcp_server_tools


class CapabilitySyncTests(unittest.TestCase):
    def test_sync_mcp_capabilities_creates_server_and_tool_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sync.sqlite3")
            initialize_db(db_path)
            add_mcp_server(
                server_id="srv1",
                name="Server One",
                connection="http://localhost:8000/mcp",
                server_type="http",
                description="test",
                db_path=db_path,
            )
            update_mcp_server_tools(
                "srv1",
                tools=[{"name": "echo", "description": "Echo tool", "schema": {"type": "object"}}],
                status="connected",
                error=None,
                last_discovered="2026-04-09T00:00:00Z",
                db_path=db_path,
            )

            result = sync_mcp_capabilities(workspace_id="ws1", db_path=db_path)
            self.assertEqual(result["servers_synced"], 1)
            self.assertEqual(result["tools_synced"], 1)

            server_cap = get_capability_by_key(workspace_id="ws1", key="mcp.server.srv1", db_path=db_path)
            tool_cap = get_capability_by_key(workspace_id="ws1", key="mcp.tool.srv1.echo", db_path=db_path)
            self.assertIsNotNone(server_cap)
            self.assertIsNotNone(tool_cap)
            self.assertEqual(server_cap["type"], "mcp_server")
            self.assertEqual(tool_cap["type"], "tool")

    def test_sync_disables_stale_managed_mcp_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "sync_stale.sqlite3")
            initialize_db(db_path)

            add_mcp_server(
                server_id="srv1",
                name="Server One",
                connection="http://localhost:8000/mcp",
                server_type="http",
                description="test",
                db_path=db_path,
            )
            update_mcp_server_tools(
                "srv1",
                tools=[{"name": "echo", "description": "Echo tool", "schema": {"type": "object"}}],
                status="connected",
                error=None,
                last_discovered="2026-04-09T00:00:00Z",
                db_path=db_path,
            )
            sync_mcp_capabilities(workspace_id="ws1", db_path=db_path)

            from kendr.persistence.mcp_store import remove_mcp_server

            remove_mcp_server("srv1", db_path=db_path)
            result = sync_mcp_capabilities(workspace_id="ws1", db_path=db_path)
            self.assertGreaterEqual(result["stale_disabled"], 1)

            all_caps = list_capabilities(workspace_id="ws1", limit=100, db_path=db_path)
            managed = [c for c in all_caps if c.get("metadata", {}).get("managed_by") == "mcp_sync"]
            self.assertTrue(managed)
            self.assertTrue(all(str(c.get("status", "")) == "disabled" for c in managed))


if __name__ == "__main__":
    unittest.main()

