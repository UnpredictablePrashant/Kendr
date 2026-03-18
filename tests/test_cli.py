import io
import json
import os
import unittest
from contextlib import redirect_stdout


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from superagent.cli import main


class CliSmokeTests(unittest.TestCase):
    def test_agents_show_json(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["agents", "show", "recon_agent", "--json"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["name"], "recon_agent")

    def test_plugins_list_json(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = main(["plugins", "list", "--json"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertIsInstance(payload, list)
        self.assertTrue(payload)


if __name__ == "__main__":
    unittest.main()
