import os
import tempfile
import unittest

from kendr.capability_registry import CapabilityRegistryService
from kendr.persistence.core import initialize_db


class CapabilityRegistryServiceTests(unittest.TestCase):
    def test_service_create_publish_and_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "capability_service.sqlite3")
            initialize_db(db_path)
            service = CapabilityRegistryService(db_path=db_path)

            auth = service.create_auth_profile(
                workspace_id="ws1",
                auth_type="oauth2",
                provider="google",
                secret_ref="vault://ws1/google/oauth",
                scopes=["gmail.read"],
            )
            policy = service.create_policy_profile(
                workspace_id="ws1",
                name="comms-policy",
                rules={"requires_authorization_flag": True},
            )

            cap_a = service.create(
                workspace_id="ws1",
                capability_type="skill",
                key="comms.digest",
                name="Communication Digest",
                description="Aggregate inbox signals across providers.",
                owner_user_id="u1",
                auth_profile_id=auth["id"],
                policy_profile_id=policy["id"],
            )
            cap_b = service.create(
                workspace_id="ws1",
                capability_type="agent",
                key="orchestrator.comms",
                name="Comms Orchestrator",
                description="Routes communication requests to available skills and tools.",
                owner_user_id="u1",
            )

            published = service.publish(cap_a["id"], workspace_id="ws1", actor_user_id="u1")
            self.assertEqual(published["status"], "active")

            relation = service.link(
                workspace_id="ws1",
                parent_capability_id=cap_b["id"],
                child_capability_id=cap_a["id"],
                relation_type="composed_of",
                actor_user_id="u1",
            )
            self.assertEqual(relation["relation_type"], "composed_of")

            listed = service.list(workspace_id="ws1", limit=20)
            self.assertEqual(len(listed), 2)

    def test_service_rejects_invalid_status_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "capability_transition.sqlite3")
            initialize_db(db_path)
            service = CapabilityRegistryService(db_path=db_path)
            cap = service.create(
                workspace_id="ws1",
                capability_type="skill",
                key="skill.one",
                name="Skill One",
                description="Test skill",
                owner_user_id="u1",
                status="error",
            )
            with self.assertRaises(ValueError):
                service.publish(cap["id"], workspace_id="ws1", actor_user_id="u1")

    def test_service_health_and_audit_observability(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "capability_observability.sqlite3")
            initialize_db(db_path)
            service = CapabilityRegistryService(db_path=db_path)
            cap = service.create(
                workspace_id="ws1",
                capability_type="tool",
                key="tool.test.health",
                name="Health Test Tool",
                description="Tool for health run coverage",
                owner_user_id="u1",
            )

            updated = service.record_health(
                cap["id"],
                workspace_id="ws1",
                actor_user_id="u1",
                status="healthy",
                latency_ms=17,
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated["health_status"], "healthy")

            health_runs = service.list_health_runs(workspace_id="ws1", capability_id=cap["id"], limit=10)
            self.assertEqual(len(health_runs), 1)
            self.assertEqual(health_runs[0]["status"], "healthy")

            audit_events = service.list_audit_events(workspace_id="ws1", capability_id=cap["id"], limit=20)
            self.assertTrue(any(evt.get("action") == "capability.health" for evt in audit_events))


if __name__ == "__main__":
    unittest.main()
