from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DefaultExperienceTests(unittest.TestCase):
    def test_ui_welcome_prompts_use_everyday_examples(self):
        ui_text = (ROOT / "kendr" / "ui_server.py").read_text(encoding="utf-8")

        for expected in (
            "Summarize this PDF and extract action items",
            "Find the latest version of our leave policy online",
            "Read this spreadsheet and tell me the totals",
            "Draft an email reply to this customer update",
            "Organize my tasks for today",
            "Plan a simple weekend trip itinerary",
        ):
            self.assertIn(expected, ui_text)

        for removed in (
            "Create a competitive intelligence brief on Stripe",
            "Build a FastAPI REST API with JWT authentication and PostgreSQL",
            "Write API tests for https://jsonplaceholder.typicode.com",
            "Dockerize a Node.js app and write a docker-compose.yml",
            "Deploy a React app to AWS S3 and CloudFront",
        ):
            self.assertNotIn(removed, ui_text)

    def test_demo_fastmcp_server_is_removed_from_repo_and_docs(self):
        self.assertFalse((ROOT / "mcp_servers" / "example_fastmcp_server.py").exists())

        integrations_text = (ROOT / "docs" / "integrations.md").read_text(encoding="utf-8")
        ui_text = (ROOT / "kendr" / "ui_server.py").read_text(encoding="utf-8")
        self.assertNotIn("example_fastmcp_server.py", integrations_text)
        self.assertNotIn("example_fastmcp_server.py", ui_text)


if __name__ == "__main__":
    unittest.main()
