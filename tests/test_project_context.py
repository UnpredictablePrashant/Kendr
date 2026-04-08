from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from kendr.project_context import ensure_kendr_md, write_kendr_md


class ProjectContextTests(unittest.TestCase):
    def test_write_kendr_md_requires_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "demo"
            root.mkdir()
            out = write_kendr_md(str(root), "# hello\n")
            self.assertTrue(out.exists())
            self.assertEqual(out.name, "kendr.md")

            missing = root / "missing"
            with self.assertRaises(FileNotFoundError):
                write_kendr_md(str(missing), "# nope\n")

    def test_ensure_kendr_md_does_not_create_literal_drive_folder_in_cwd(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.getcwd()
            os.chdir(tmpdir)
            try:
                drive_prefix = "X"
                marker = uuid.uuid4().hex
                fake_windows_root = f"{drive_prefix}:/repo-{marker}"
                content = ensure_kendr_md(fake_windows_root, "repo")
            finally:
                os.chdir(previous)

        self.assertIn("Directory not found", content)
        self.assertFalse((Path(tmpdir) / f"{drive_prefix}:").exists())


if __name__ == "__main__":
    unittest.main()
