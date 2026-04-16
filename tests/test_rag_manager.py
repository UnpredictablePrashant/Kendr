import importlib
import os
import tempfile
import unittest
from unittest.mock import patch


class RagManagerResearchTests(unittest.TestCase):
    def _load_module(self, config_dir: str):
        with patch.dict(os.environ, {"KENDR_CONFIG_DIR": config_dir}, clear=False):
            import kendr.rag_manager as rag_manager

            return importlib.reload(rag_manager)

    def test_resolve_kb_by_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rag_manager = self._load_module(tmpdir)
            kb = rag_manager.create_kb("finance-kb")

            resolved = rag_manager.resolve_kb(kb["id"])

            self.assertEqual(resolved["id"], kb["id"])

    def test_resolve_kb_by_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rag_manager = self._load_module(tmpdir)
            kb = rag_manager.create_kb("finance-kb")

            resolved = rag_manager.resolve_kb("finance-kb")

            self.assertEqual(resolved["id"], kb["id"])

    def test_resolve_kb_uses_active_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rag_manager = self._load_module(tmpdir)
            rag_manager.create_kb("alpha")
            kb = rag_manager.create_kb("beta")
            rag_manager.set_active_kb(kb["id"])

            resolved = rag_manager.resolve_kb("")

            self.assertEqual(resolved["id"], kb["id"])

    def test_resolve_kb_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rag_manager = self._load_module(tmpdir)

            with self.assertRaises(ValueError) as exc:
                rag_manager.resolve_kb("missing-kb")

        self.assertIn("Knowledge base not found", str(exc.exception))

    def test_resolve_kb_requires_indexed_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rag_manager = self._load_module(tmpdir)
            rag_manager.create_kb("finance-kb")

            with self.assertRaises(ValueError) as exc:
                rag_manager.resolve_kb("finance-kb", require_indexed=True)

        self.assertIn("not indexed", str(exc.exception))

    def test_build_research_grounding_returns_prompt_ready_packet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rag_manager = self._load_module(tmpdir)
            kb = rag_manager.create_kb("finance-kb")
            rag_manager.update_kb_field(kb["id"], status="indexed")

            fake_hits = [
                {
                    "source": "file:///tmp/report.md",
                    "text": "Revenue grew 20 percent year over year.",
                    "score": 0.91,
                    "payload": {"source_type": "local_file", "chunk_index": 0},
                },
                {
                    "source": "file:///tmp/report.md",
                    "text": "Revenue grew 20 percent year over year.",
                    "score": 0.90,
                    "payload": {"source_type": "local_file", "chunk_index": 0},
                },
                {
                    "source": "db://customers#schema",
                    "text": "Customer table contains segment and region columns.",
                    "score": 0.82,
                    "payload": {"source_type": "database_schema", "chunk_index": 1},
                },
            ]

            with patch.object(
                rag_manager,
                "query_kb",
                return_value={
                    "kb_id": kb["id"],
                    "kb_name": kb["name"],
                    "query": "market structure",
                    "hits": fake_hits,
                    "citations": [],
                    "total_hits": len(fake_hits),
                    "algorithm": "none",
                },
            ):
                packet = rag_manager.build_research_grounding("market structure", kb_ref=kb["id"], top_k=8)

        self.assertEqual(packet["kb_id"], kb["id"])
        self.assertEqual(packet["kb_name"], "finance-kb")
        self.assertEqual(packet["hit_count"], 3)
        self.assertEqual(len(packet["citations"]), 2)
        self.assertIn("Knowledge Base Grounding", packet["prompt_context"])
        self.assertIn("file:///tmp/report.md", packet["deduped_source_ids"])
