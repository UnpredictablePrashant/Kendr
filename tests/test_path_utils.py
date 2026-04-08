from __future__ import annotations

import os
import unittest
from pathlib import Path

from kendr.path_utils import normalize_host_path_str


class PathUtilsTests(unittest.TestCase):
    def test_normalize_relative_path_uses_base_directory(self):
        result = normalize_host_path_str("logs/kendr", base_dir="/tmp")
        self.assertEqual(result, str(Path("/tmp/logs/kendr").resolve()))

    def test_normalize_windows_drive_path_on_non_windows_hosts(self):
        source = "D:/repo/subdir"
        result = normalize_host_path_str(source)
        if os.name == "nt":
            self.assertTrue(result.lower().endswith("\\repo\\subdir"))
        else:
            self.assertEqual(result, str(Path("/mnt/d/repo/subdir").resolve()))


if __name__ == "__main__":
    unittest.main()
