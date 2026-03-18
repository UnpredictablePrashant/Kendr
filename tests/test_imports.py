import os
import importlib.util
import unittest


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


class ImportSmokeTests(unittest.TestCase):
    def test_import_runtime_entrypoints(self):
        import app  # noqa: F401
        import gateway_server  # noqa: F401
        import setup_ui  # noqa: F401

    @unittest.skipUnless(importlib.util.find_spec("fastmcp") is not None, "fastmcp is not installed in the active interpreter")
    def test_import_mcp_servers(self):
        import mcp_servers.cve_server  # noqa: F401
        import mcp_servers.http_fuzzing_server  # noqa: F401
        import mcp_servers.nmap_server  # noqa: F401
        import mcp_servers.research_server  # noqa: F401
        import mcp_servers.screenshot_server  # noqa: F401
        import mcp_servers.vector_server  # noqa: F401
        import mcp_servers.zap_server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
