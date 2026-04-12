from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kendr.secret_store as secret_store


class _FakeBackend:
    name = "fake-os"

    def __init__(self):
        self.values: dict[str, object] = {}

    def put(self, ref: str, value) -> None:
        self.values[ref] = value

    def get(self, ref: str):
        return self.values.get(ref, secret_store._SECRET_MISSING)

    def delete(self, ref: str) -> bool:
        return self.values.pop(ref, None) is not None


class _BrokenBackend:
    name = "broken-os"

    def put(self, ref: str, value) -> None:
        raise RuntimeError("backend_unavailable")

    def get(self, ref: str):
        raise RuntimeError("backend_unavailable")

    def delete(self, ref: str) -> bool:
        raise RuntimeError("backend_unavailable")


class SecretStoreMigrationTests(unittest.TestCase):
    def tearDown(self) -> None:
        secret_store._reset_secret_backend_cache()

    def test_legacy_secret_migrates_into_selected_backend_on_first_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = secret_store.build_secret_ref("setup", "openai", "OPENAI_API_KEY")
            path = Path(tmp) / "secret_store.json"
            path.write_text(
                json.dumps({"version": 1, "secrets": {ref: "sk-legacy"}}),
                encoding="utf-8",
            )
            backend = _FakeBackend()
            with patch.dict(os.environ, {"KENDR_HOME": tmp}, clear=False):
                with patch("kendr.secret_store._build_secret_backend", return_value=backend):
                    secret_store._reset_secret_backend_cache()
                    value = secret_store.get_secret(ref, default="")

            self.assertEqual(value, "sk-legacy")
            self.assertEqual(backend.values[ref], "sk-legacy")
            self.assertFalse(path.exists(), "Legacy store should be cleared after successful migration.")

    def test_put_secret_uses_file_fallback_when_backend_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = secret_store.build_secret_ref("provider", "google", "tokens")
            path = Path(tmp) / "secret_store.json"
            with patch.dict(os.environ, {"KENDR_HOME": tmp}, clear=False):
                with patch("kendr.secret_store._build_secret_backend", return_value=_BrokenBackend()):
                    secret_store._reset_secret_backend_cache()
                    secret_store.put_secret(ref, {"access_token": "tok-123"})
                    value = secret_store.get_secret(ref, default={})

            self.assertEqual(value, {"access_token": "tok-123"})
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["secrets"][ref]["access_token"], "tok-123")

    def test_delete_secret_clears_selected_backend_and_legacy_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = secret_store.build_secret_ref("mcp", "server-1", "auth_token")
            path = Path(tmp) / "secret_store.json"
            path.write_text(
                json.dumps({"version": 1, "secrets": {ref: "legacy-token"}}),
                encoding="utf-8",
            )
            backend = _FakeBackend()
            backend.values[ref] = "new-token"
            with patch.dict(os.environ, {"KENDR_HOME": tmp}, clear=False):
                with patch("kendr.secret_store._build_secret_backend", return_value=backend):
                    secret_store._reset_secret_backend_cache()
                    deleted = secret_store.delete_secret(ref)

            self.assertTrue(deleted)
            self.assertNotIn(ref, backend.values)
            self.assertFalse(path.exists(), "Legacy store should be cleared when the last migrated secret is deleted.")


if __name__ == "__main__":
    unittest.main()
