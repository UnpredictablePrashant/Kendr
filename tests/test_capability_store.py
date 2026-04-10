import os
import tempfile
import unittest

from kendr.persistence import (
    add_capability_relation,
    create_auth_profile,
    create_capability,
    create_policy_profile,
    get_capability,
    insert_capability_audit_event,
    list_auth_profiles,
    list_capability_audit_events,
    list_capability_health_runs,
    list_capabilities,
    list_policy_profiles,
    set_capability_health,
    update_capability,
)
from kendr.persistence.core import _connect, initialize_db


class CapabilityStoreTests(unittest.TestCase):
    def test_phase0_capability_schema_and_crud(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "capabilities.sqlite3")
            initialize_db(db_path)

            auth = create_auth_profile(
                workspace_id="ws1",
                auth_type="api_key",
                provider="github",
                secret_ref="vault://ws1/github/token",
                scopes=["repo:read"],
                db_path=db_path,
            )
            policy = create_policy_profile(
                workspace_id="ws1",
                name="readonly-policy",
                rules={"deny_write": True},
                db_path=db_path,
            )
            cap = create_capability(
                workspace_id="ws1",
                capability_type="api",
                key="github.issue.read",
                name="GitHub Issue Reader",
                description="Read issue data from GitHub repos.",
                owner_user_id="u1",
                auth_profile_id=auth["id"],
                policy_profile_id=policy["id"],
                tags=["github", "issues"],
                metadata={"source": "openapi"},
                schema_in={"type": "object"},
                schema_out={"type": "object"},
                db_path=db_path,
            )

            fetched = get_capability(cap["id"], db_path=db_path)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["type"], "api")
            self.assertEqual(fetched["key"], "github.issue.read")
            self.assertIn("github", fetched["tags"])

            updated = update_capability(
                cap["id"],
                status="verified",
                visibility="org",
                db_path=db_path,
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated["status"], "verified")
            self.assertEqual(updated["visibility"], "org")

            set_capability_health(
                cap["id"],
                workspace_id="ws1",
                status="healthy",
                latency_ms=42,
                db_path=db_path,
            )
            healthy = get_capability(cap["id"], db_path=db_path)
            self.assertEqual(healthy["health_status"], "healthy")

            rel = add_capability_relation(
                workspace_id="ws1",
                parent_capability_id=cap["id"],
                child_capability_id=cap["id"],
                relation_type="depends_on",
                db_path=db_path,
            )
            self.assertEqual(rel["relation_type"], "depends_on")

            event = insert_capability_audit_event(
                workspace_id="ws1",
                actor_user_id="u1",
                action="capability.test",
                capability_id=cap["id"],
                payload={"ok": True},
                db_path=db_path,
            )
            self.assertEqual(event["action"], "capability.test")
            self.assertTrue(event["payload"]["ok"])

            listed = list_capabilities(workspace_id="ws1", capability_type="api", db_path=db_path)
            self.assertEqual(len(listed), 1)
            self.assertEqual(len(list_auth_profiles(workspace_id="ws1", db_path=db_path)), 1)
            self.assertEqual(len(list_policy_profiles(workspace_id="ws1", db_path=db_path)), 1)
            self.assertEqual(len(list_capability_health_runs(workspace_id="ws1", capability_id=cap["id"], db_path=db_path)), 1)
            self.assertEqual(len(list_capability_audit_events(workspace_id="ws1", capability_id=cap["id"], db_path=db_path)), 1)

            with _connect(db_path) as conn:
                health_rows = conn.execute("SELECT COUNT(*) AS c FROM capability_health_runs").fetchone()["c"]
                audit_rows = conn.execute("SELECT COUNT(*) AS c FROM capability_audit_events").fetchone()["c"]
                self.assertEqual(int(health_rows), 1)
                self.assertEqual(int(audit_rows), 1)


if __name__ == "__main__":
    unittest.main()
