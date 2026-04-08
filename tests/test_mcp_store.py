import unittest

from kendr.persistence.mcp_store import _migrated_flag_path


class MCPStoreTests(unittest.TestCase):
    def test_migrated_flag_path_is_db_specific(self):
        a = _migrated_flag_path("/tmp/a.sqlite3")
        b = _migrated_flag_path("/tmp/b.sqlite3")
        self.assertNotEqual(a, b)
        self.assertIn("mcp_migrated_", a)
        self.assertTrue(a.endswith(".flag"))


if __name__ == "__main__":
    unittest.main()
