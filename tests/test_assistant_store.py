from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import os

from kendr.persistence.assistant_store import (
    create_assistant,
    delete_assistant,
    get_assistant,
    list_assistants,
    update_assistant,
)
from kendr.persistence.core import initialize_db


class TestAssistantStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "assistants.sqlite3")
        self.prev_auto_migrate = os.environ.get("KENDR_DB_AUTO_MIGRATE")
        os.environ["KENDR_DB_AUTO_MIGRATE"] = "0"
        initialize_db(self.db_path)

    def tearDown(self) -> None:
        if self.prev_auto_migrate is None:
            os.environ.pop("KENDR_DB_AUTO_MIGRATE", None)
        else:
            os.environ["KENDR_DB_AUTO_MIGRATE"] = self.prev_auto_migrate
        self.tmpdir.cleanup()

    def test_create_and_get_assistant(self) -> None:
        assistant = create_assistant(
            workspace_id="default",
            owner_user_id="tester",
            name="Support Assistant",
            description="Handles support questions",
            goal="Answer support issues",
            attached_capabilities=[{"capability_id": "cap-1", "name": "Docs Search"}],
            memory_config={"summary": "Use docs"},
            db_path=self.db_path,
        )

        fetched = get_assistant(assistant["assistant_id"], db_path=self.db_path)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], "Support Assistant")
        self.assertEqual(fetched["attached_capabilities"][0]["name"], "Docs Search")
        self.assertEqual(fetched["memory_config"]["summary"], "Use docs")

    def test_update_assistant(self) -> None:
        assistant = create_assistant(
            workspace_id="default",
            owner_user_id="tester",
            name="Research Assistant",
            db_path=self.db_path,
        )

        updated = update_assistant(
            assistant["assistant_id"],
            description="Updated description",
            status="active",
            memory_config={"summary": "Remember project notes"},
            db_path=self.db_path,
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["description"], "Updated description")
        self.assertEqual(updated["status"], "active")
        self.assertEqual(updated["memory_config"]["summary"], "Remember project notes")

    def test_list_and_delete_assistants(self) -> None:
        first = create_assistant(
            workspace_id="default",
            owner_user_id="tester",
            name="Alpha Assistant",
            db_path=self.db_path,
        )
        create_assistant(
            workspace_id="default",
            owner_user_id="tester",
            name="Beta Assistant",
            status="active",
            db_path=self.db_path,
        )

        active_only = list_assistants(workspace_id="default", status="active", db_path=self.db_path)
        self.assertEqual(len(active_only), 1)
        self.assertEqual(active_only[0]["name"], "Beta Assistant")

        ok = delete_assistant(first["assistant_id"], db_path=self.db_path)
        self.assertTrue(ok)
        self.assertIsNone(get_assistant(first["assistant_id"], db_path=self.db_path))


if __name__ == "__main__":
    unittest.main()
