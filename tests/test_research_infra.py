import os
import sys
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch, MagicMock

from tasks.research_infra import fetch_search_results, llm_text, parse_document, parse_documents


class ResearchInfraTests(unittest.TestCase):
    def test_llm_text_sanitizes_unpaired_surrogates_before_invoke(self):
        bad_prompt = "bad-\ud83c-prompt"

        with patch("tasks.research_infra.llm.invoke", return_value=MagicMock(content="ok")) as mock_invoke:
            result = llm_text(bad_prompt, max_retries=1)

        self.assertEqual(result, "ok")
        self.assertEqual(mock_invoke.call_count, 1)
        called_prompt = mock_invoke.call_args.args[0]
        self.assertNotIn("\ud83c", called_prompt)
        self.assertIn("\uFFFD", called_prompt)

    def test_fetch_search_results_falls_back_to_duckduckgo_and_fetches_evidence(self):
        with (
            patch.dict(os.environ, {"SERP_API_KEY": "", "KENDR_BROWSER_USE_SEARCH_ENABLED": "0"}, clear=False),
            patch("tasks.research_infra._browser_use_server_enabled", return_value=False),
            patch(
                "tasks.research_infra.duckduckgo_html_search",
                return_value={
                    "results": [
                        {
                            "title": "Fallback result",
                            "url": "https://example.com/a",
                            "snippet": "snippet a",
                            "source": "DuckDuckGo",
                            "date": "",
                        }
                    ]
                },
            ),
            patch(
                "tasks.research_infra.fetch_url_content",
                return_value={"content_type": "text/html", "text": "evidence body"},
            ),
        ):
            result = fetch_search_results("fallback query", num=3, fetch_pages=1)

        self.assertEqual(result["provider"], "duckduckgo_html")
        self.assertEqual(result["providers_tried"], ["duckduckgo_html"])
        self.assertEqual(result["results"][0]["url"], "https://example.com/a")
        self.assertEqual(result["viewed_pages"][0]["url"], "https://example.com/a")
        self.assertIn("evidence body", result["viewed_pages"][0]["excerpt"])

    def test_fetch_search_results_uses_browser_use_before_free_search_when_serpapi_missing(self):
        with (
            patch.dict(os.environ, {"SERP_API_KEY": "", "KENDR_BROWSER_USE_SEARCH_ENABLED": "1"}, clear=False),
            patch("tasks.research_infra._browser_use_server_enabled", return_value=True),
            patch(
                "tasks.research_infra.browser_use_search",
                return_value={
                    "results": [
                        {
                            "title": "Browser Use result",
                            "url": "https://example.com/b",
                            "snippet": "snippet b",
                            "source": "browser-use MCP",
                            "date": "",
                        }
                    ]
                },
            ),
            patch(
                "tasks.research_infra.fetch_url_content",
                return_value={"content_type": "text/html", "text": "browser evidence"},
            ),
        ):
            result = fetch_search_results("browser fallback", num=2, fetch_pages=1)

        self.assertEqual(result["provider"], "browser_use_mcp")
        self.assertEqual(result["providers_tried"], ["browser_use_mcp"])
        self.assertEqual(result["results"][0]["url"], "https://example.com/b")

    def test_fetch_search_results_prefers_serpapi_when_enabled(self):
        with (
            patch.dict(os.environ, {"SERP_API_KEY": "test-key", "KENDR_BROWSER_USE_SEARCH_ENABLED": "1"}, clear=False),
            patch(
                "tasks.research_infra.serp_search",
                return_value={
                    "organic_results": [
                        {"title": "Serp result", "link": "https://example.com/serp", "snippet": "serp snippet", "source": "Google"},
                    ]
                },
            ),
            patch("tasks.research_infra._browser_use_server_enabled", return_value=True),
            patch("tasks.research_infra.browser_use_search") as mock_browser_use,
            patch(
                "tasks.research_infra.fetch_url_content",
                return_value={"content_type": "text/html", "text": "serp evidence"},
            ),
        ):
            result = fetch_search_results("serp first", num=2, fetch_pages=1)

        self.assertEqual(result["provider"], "serpapi")
        self.assertEqual(result["providers_tried"], ["serpapi"])
        self.assertFalse(mock_browser_use.called)

    def test_parse_document_uses_excel_pdf_fallback_when_primary_read_fails(self):
        with TemporaryDirectory() as tmp:
            excel_path = Path(tmp) / "model.xlsx"
            excel_path.write_bytes(b"placeholder")

            with (
                patch("tasks.research_infra._extract_xlsx_text", side_effect=RuntimeError("primary failed")),
                patch(
                    "tasks.research_infra._extract_excel_text_via_pdf_fallback",
                    return_value=(
                        "Revenue 100\nMargin 55%",
                        {
                            "type": "xlsx",
                            "reader": "soffice_pdf_fallback",
                            "fallback_source": "pdf_conversion",
                            "fallback_pdf_pages": 1,
                        },
                    ),
                ),
            ):
                result = parse_document(str(excel_path))

        self.assertIn("Revenue 100", result["text"])
        self.assertEqual(result["metadata"]["reader"], "soffice_pdf_fallback")
        self.assertEqual(result["metadata"]["fallback_source"], "pdf_conversion")

    def test_parse_documents_continue_on_error_records_fallback_failure(self):
        with TemporaryDirectory() as tmp:
            excel_path = Path(tmp) / "model.xlsx"
            excel_path.write_bytes(b"placeholder")

            with (
                patch("tasks.research_infra._extract_xlsx_text", side_effect=RuntimeError("primary failed")),
                patch(
                    "tasks.research_infra._extract_excel_text_via_pdf_fallback",
                    side_effect=RuntimeError("fallback failed"),
                ),
            ):
                results = parse_documents([str(excel_path)], continue_on_error=True)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["metadata"]["type"], "xlsx")
        self.assertIn("fallback failed", results[0]["metadata"].get("error", ""))


    def test_parse_document_routes_pptx_to_pptx_extractor(self):
        with TemporaryDirectory() as tmp:
            pptx_path = Path(tmp) / "slides.pptx"
            pptx_path.write_bytes(b"placeholder")

            with patch(
                "tasks.research_infra._extract_pptx_text",
                return_value=("Slide 1 content\nSlide 2 content", {"type": "pptx", "reader": "python-pptx", "slides": 2}),
            ) as mock_extract:
                result = parse_document(str(pptx_path))

        mock_extract.assert_called_once()
        self.assertEqual(result["metadata"]["type"], "pptx")
        self.assertIn("Slide 1 content", result["text"])

    def test_parse_document_routes_xlsx_to_xlsx_extractor(self):
        with TemporaryDirectory() as tmp:
            xlsx_path = Path(tmp) / "data.xlsx"
            xlsx_path.write_bytes(b"placeholder")

            with patch(
                "tasks.research_infra._extract_xlsx_text",
                return_value=("col1, col2\nval1, val2", {"type": "xlsx", "reader": "openpyxl", "sheets": 1}),
            ) as mock_extract:
                result = parse_document(str(xlsx_path))

        mock_extract.assert_called_once()
        self.assertEqual(result["metadata"]["type"], "xlsx")
        self.assertIn("col1", result["text"])


class VectorBackendSelectionTests(unittest.TestCase):
    def setUp(self):
        import tasks.vector_backends as vb
        self._orig_cache = vb._BACKEND_CACHE
        vb._BACKEND_CACHE = None

    def tearDown(self):
        import tasks.vector_backends as vb
        vb._BACKEND_CACHE = self._orig_cache

    def test_chroma_selected_when_qdrant_url_not_set(self):
        import tasks.vector_backends as vb

        env = {k: v for k, v in os.environ.items() if k != "QDRANT_URL"}
        with patch.dict(os.environ, env, clear=True):
            vb._BACKEND_CACHE = None
            backend = vb.get_vector_backend()
        self.assertIsInstance(backend, vb.ChromaBackend)

    def test_chroma_selected_when_qdrant_url_set_but_unreachable(self):
        import tasks.vector_backends as vb

        with patch.dict(os.environ, {"QDRANT_URL": "http://unreachable-xyz:6333"}):
            with patch("tasks.vector_backends._qdrant_reachable", return_value=False):
                vb._BACKEND_CACHE = None
                backend = vb.get_vector_backend()
        self.assertIsInstance(backend, vb.ChromaBackend)

    def test_qdrant_selected_when_qdrant_url_set_and_reachable(self):
        import tasks.vector_backends as vb

        with patch.dict(os.environ, {"QDRANT_URL": "http://qdrant-test:6333"}):
            with patch("tasks.vector_backends._qdrant_reachable", return_value=True):
                vb._BACKEND_CACHE = None
                backend = vb.get_vector_backend()
        self.assertIsInstance(backend, vb.QdrantBackend)

    def test_backend_result_is_cached_after_first_call(self):
        import tasks.vector_backends as vb

        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "QDRANT_URL"}, clear=True):
            vb._BACKEND_CACHE = None
            b1 = vb.get_vector_backend()
            b2 = vb.get_vector_backend()
        self.assertIs(b1, b2)

    def test_chroma_backend_upsert_and_search_roundtrip(self):
        import tasks.vector_backends as vb

        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"KENDR_WORKING_DIR": tmp, **{k: v for k, v in os.environ.items() if k != "QDRANT_URL"}}, clear=True):
                backend = vb.ChromaBackend()
                backend.ensure_collection("test_rt", vector_size=3)
                records = [
                    {"source": "s1", "text": "hello world"},
                    {"source": "s2", "text": "goodbye world"},
                ]
                vectors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
                result = backend.upsert("test_rt", records, vectors)
                self.assertEqual(result["indexed"], 2)
                hits = backend.search("test_rt", [1.0, 0.0, 0.0], top_k=1)
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["source"], "s1")


if __name__ == "__main__":
    unittest.main()
