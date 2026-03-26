import os
import unittest
from unittest.mock import patch


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from superagent.discovery import build_registry
from superagent.setup import build_setup_snapshot


class SetupRegistryTests(unittest.TestCase):
    def test_setup_snapshot_includes_agent_and_service_status(self):
        registry = build_registry()
        snapshot = build_setup_snapshot(registry.agent_cards())
        self.assertIn("services", snapshot)
        self.assertIn("agents", snapshot)
        self.assertIn("available_agents", snapshot)
        self.assertIn("openai", snapshot["services"])

    def test_scanner_agent_disabled_without_scan_tools(self):
        registry = build_registry()
        with patch("shutil.which", return_value=None):
            snapshot = build_setup_snapshot(registry.agent_cards())
        scanner_status = snapshot["agents"].get("scanner_agent", {})
        self.assertIn("available", scanner_status)
        self.assertFalse(scanner_status["available"])
        self.assertIn("nmap_or_zap", scanner_status.get("missing_services", []))


if __name__ == "__main__":
    unittest.main()
