import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kendr.persistence.core as core
from kendr.persistence.core import initialize_db, list_legacy_databases, migrate_legacy_databases, resolve_db_path


def _seed_legacy_runs_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                user_query TEXT,
                started_at TEXT,
                status TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO runs(run_id, user_query, started_at, status) VALUES(?, ?, ?, ?)",
            ("legacy-run-1", "legacy query", "2026-04-08T00:00:00Z", "completed"),
        )
        conn.commit()
    finally:
        conn.close()


class PersistenceCoreTests(unittest.TestCase):
    def test_migrate_legacy_database_copies_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = os.path.join(tmpdir, "central.sqlite3")
            legacy_db = os.path.join(tmpdir, "nested", "output", "agent_workflow.sqlite3")
            _seed_legacy_runs_db(legacy_db)

            initialize_db(target_db)
            result = migrate_legacy_databases(target_db, legacy_paths=[legacy_db])

            self.assertEqual(result["target_db_path"], str(Path(target_db).resolve()))
            self.assertEqual(len(result["migrated"]), 1)
            self.assertEqual(result["migrated"][0]["source_path"], str(Path(legacy_db).resolve()))

            conn = sqlite3.connect(target_db)
            try:
                row = conn.execute(
                    "SELECT run_id, user_query, status FROM runs WHERE run_id = ?",
                    ("legacy-run-1",),
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("legacy-run-1", "legacy query", "completed"))

    def test_migrate_legacy_database_can_delete_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = os.path.join(tmpdir, "central.sqlite3")
            legacy_db = os.path.join(tmpdir, "legacy", "output", "agent_workflow.sqlite3")
            _seed_legacy_runs_db(legacy_db)

            initialize_db(target_db)
            result = migrate_legacy_databases(target_db, legacy_paths=[legacy_db], delete_legacy=True)

            self.assertEqual(len(result["migrated"]), 1)
            self.assertFalse(os.path.exists(legacy_db))

    def test_resolve_db_path_prefers_env_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_db = os.path.join(tmpdir, "env.sqlite3")
            with patch.dict(os.environ, {"KENDR_DB_PATH": env_db}, clear=False):
                self.assertEqual(resolve_db_path(), str(Path(env_db).resolve()))

    def test_resolve_db_path_uses_kendr_home_when_no_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"KENDR_DB_PATH": "", "KENDR_HOME": tmpdir}, clear=False):
                expected = str((Path(tmpdir).resolve() / "agent_workflow.sqlite3"))
                self.assertEqual(resolve_db_path(), expected)

    def test_list_legacy_databases_includes_env_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = os.path.join(tmpdir, "central.sqlite3")
            legacy_a = os.path.join(tmpdir, "legacy-a.sqlite3")
            legacy_b = os.path.join(tmpdir, "legacy-b.sqlite3")
            _seed_legacy_runs_db(legacy_a)
            _seed_legacy_runs_db(legacy_b)

            joined = os.pathsep.join([legacy_a, legacy_b])
            with patch.dict(os.environ, {"KENDR_DB_LEGACY_PATHS": joined}, clear=False):
                found = set(list_legacy_databases(target_db))

            self.assertIn(str(Path(legacy_a).resolve()), found)
            self.assertIn(str(Path(legacy_b).resolve()), found)

    def test_list_legacy_databases_skips_workspace_defaults_for_custom_target(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = os.path.join(tmpdir, "central.sqlite3")
            workspace_default = str((Path.cwd() / "output" / "agent_workflow.sqlite3").resolve())
            with patch.dict(
                os.environ,
                {
                    "KENDR_DB_LEGACY_PATHS": "",
                    "KENDR_WORKING_DIR": "",
                    "KENDR_DB_SEARCH_ROOTS": "",
                    "KENDR_DB_ENABLE_RECURSIVE_SEARCH": "0",
                },
                clear=False,
            ):
                found = set(list_legacy_databases(target_db))

            self.assertNotIn(workspace_default, found)

    def test_auto_migration_retries_after_transient_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = os.path.join(tmpdir, "central.sqlite3")
            calls = {"count": 0}

            def _fake_migrate(db_path: str, *, legacy_paths=None, delete_legacy=False):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("transient failure")
                return {"target_db_path": db_path, "migrated": [], "skipped": [], "deleted_legacy": False}

            with patch.dict(os.environ, {"KENDR_DB_AUTO_MIGRATE": "true"}, clear=False):
                with patch.object(core, "migrate_legacy_databases", side_effect=_fake_migrate):
                    core._MIGRATED_PRIMARY_DB_PATHS.clear()
                    core._migrate_legacy_databases_once(target_db)
                    core._migrate_legacy_databases_once(target_db)

            self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
