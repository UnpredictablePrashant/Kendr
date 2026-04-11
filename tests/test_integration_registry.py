from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from kendr.integration_registry import (
    AGENT_INTEGRATION_MAP,
    IntegrationCard,
    check_agent_integration_config,
    get_integration,
    list_integrations,
)
from kendr.plugin_manager import (
    AGENT_PLUGIN_MAP,
    PluginCard,
    check_agent_plugin_config,
    get_plugin,
    list_plugins,
)


class IntegrationRegistryTests(unittest.TestCase):
    def test_canonical_integration_listing_returns_cards(self):
        items = list_integrations()
        self.assertTrue(items)
        self.assertIsInstance(items[0], IntegrationCard)
        self.assertEqual(items[0].to_dict()["id"], items[0].id)

    def test_plugin_manager_compatibility_shim_reuses_integration_surface(self):
        items = list_plugins()
        self.assertTrue(items)
        self.assertIsInstance(items[0], PluginCard)
        self.assertEqual(AGENT_PLUGIN_MAP, AGENT_INTEGRATION_MAP)
        self.assertEqual(get_plugin("github"), get_integration("github"))

    def test_agent_config_check_uses_integration_mapping(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            integration_id, missing_vars, needs_config, hint = check_agent_integration_config("github_issue_agent")

        self.assertEqual(integration_id, "github")
        self.assertTrue(needs_config)
        self.assertIn("GITHUB_TOKEN", missing_vars)
        self.assertIn("Requires github credentials", hint)

        legacy_result = check_agent_plugin_config("github_issue_agent")
        self.assertEqual(legacy_result[0], integration_id)
        self.assertEqual(legacy_result[1], missing_vars)
        self.assertEqual(legacy_result[2], needs_config)


if __name__ == "__main__":
    unittest.main()
