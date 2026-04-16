import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from tasks.intelligence_tasks import document_ingestion_agent, local_drive_agent, ocr_agent


class LocalDriveAgentTests(unittest.TestCase):
    def test_local_drive_agent_output_includes_catalog_summary(self):
        with TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, "financials.txt")
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write("sample")

            state = {
                "user_query": "Catalog the local files and summarize the evidence.",
                "current_objective": "Catalog the local files and summarize the evidence.",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_index_to_memory": False,
            }

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch(
                    "tasks.intelligence_tasks.parse_documents",
                    return_value=[
                        {
                            "text": "Revenue grew and margins improved.",
                            "metadata": {"type": "txt", "error": ""},
                            "path": file_path,
                        }
                    ],
                ),
                patch(
                    "tasks.intelligence_tasks.llm_text",
                    side_effect=["Document summary", "Rollup summary"],
                ),
            ):
                result = local_drive_agent(state)

        self.assertIn("Catalog Summary", result["draft_response"])
        self.assertIn("File Type Counts", result["draft_response"])
        self.assertIn("Representative Files", result["draft_response"])
        self.assertIn("Structured Manifest", result["draft_response"])
        self.assertIn("Extension Handler Routing", result["draft_response"])
        self.assertIn("Rollup Findings", result["draft_response"])
        self.assertIn("local_drive_manifest", result)
        self.assertIn("local_drive_handler_routes", result)

    def test_local_drive_agent_manifest_includes_file_and_folder_metadata(self):
        with TemporaryDirectory() as tmp:
            nested_dir = os.path.join(tmp, "nested")
            os.makedirs(nested_dir, exist_ok=True)
            selected_path = os.path.join(nested_dir, "financials.txt")
            excluded_path = os.path.join(tmp, "ignore.bin")
            with open(selected_path, "w", encoding="utf-8") as handle:
                handle.write("sample")
            with open(excluded_path, "w", encoding="utf-8") as handle:
                handle.write("raw")

            state = {
                "user_query": "Catalog the local files and summarize the evidence.",
                "current_objective": "Catalog the local files and summarize the evidence.",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_extensions": "txt",
                "local_drive_index_to_memory": False,
            }

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch(
                    "tasks.intelligence_tasks.parse_documents",
                    return_value=[
                        {
                            "text": "Revenue grew and margins improved.",
                            "metadata": {"type": "txt", "error": ""},
                            "path": selected_path,
                        }
                    ],
                ),
                patch(
                    "tasks.intelligence_tasks.llm_text",
                    side_effect=["Document summary", "Rollup summary"],
                ),
            ):
                result = local_drive_agent(state)

        manifest = result["local_drive_manifest"]
        self.assertEqual(manifest["selected_file_count"], 1)
        self.assertEqual(manifest["file_count"], 2)
        self.assertGreaterEqual(manifest["folder_count"], 2)
        selected_entry = next(item for item in manifest["files"] if item["path"] == selected_path)
        excluded_entry = next(item for item in manifest["files"] if item["path"] == excluded_path)
        folder_entry = next(item for item in manifest["folders"] if item["path"] == nested_dir)
        self.assertTrue(selected_entry["selected_for_processing"])
        self.assertEqual(excluded_entry["exclusion_reason"], "unsupported_extension")
        self.assertEqual(folder_entry["entry_type"], "directory")
        self.assertIn("modified_at", selected_entry)
        self.assertIn("size_bytes", selected_entry)

    def test_document_ingestion_agent_uses_local_drive_documents_when_paths_missing(self):
        state = {
            "user_query": "Classify inventoried files.",
            "current_objective": "Classify inventoried files.",
            "local_drive_documents": [
                {
                    "path": "/tmp/financials.txt",
                    "text": "Revenue increased; margin improved.",
                    "metadata": {"type": "txt", "error": ""},
                }
            ],
            "document_index_to_memory": False,
        }

        with (
            patch("tasks.a2a_agent_utils.record_work_note"),
            patch("tasks.intelligence_tasks.log_task_update"),
            patch("tasks.intelligence_tasks.write_text_file"),
            patch("tasks.intelligence_tasks._maybe_upsert_memory"),
            patch("tasks.intelligence_tasks.parse_documents") as parse_documents_mock,
            patch("tasks.intelligence_tasks.llm_text", return_value="Document ingestion summary"),
        ):
            result = document_ingestion_agent(state)

        parse_documents_mock.assert_not_called()
        self.assertIn("Document Ingestion Confirmation", result["document_summary"])
        self.assertIn("Findings", result["document_summary"])
        self.assertIn("Document ingestion summary", result["document_summary"])
        self.assertEqual(len(result["documents"]), 1)
        self.assertEqual(result.get("document_ingestion_source"), "local_drive_documents")
        report = result.get("document_ingestion_report", {})
        self.assertEqual(len(report.get("attempted_files", [])), 1)
        self.assertEqual(len(report.get("successful_files", [])), 1)
        self.assertEqual(len(report.get("failed_files", [])), 0)

    def test_document_ingestion_agent_emits_coverage_and_error_breakdown(self):
        with TemporaryDirectory() as tmp:
            good_path = os.path.join(tmp, "good.txt")
            bad_path = os.path.join(tmp, "bad.pdf")
            with open(good_path, "w", encoding="utf-8") as handle:
                handle.write("ok")
            with open(bad_path, "w", encoding="utf-8") as handle:
                handle.write("bad")

            state = {
                "user_query": "Ingest all documents from the selected path.",
                "current_objective": "Ingest all documents from the selected path.",
                "local_drive_paths": [tmp],
                "document_paths": [good_path, bad_path],
                "document_working_directory": tmp,
                "document_index_to_memory": False,
            }

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch(
                    "tasks.intelligence_tasks.parse_documents",
                    return_value=[
                        {"path": good_path, "text": "Revenue and margin details", "metadata": {"type": "txt", "error": ""}},
                        {"path": bad_path, "text": "", "metadata": {"type": "pdf", "error": "decode_failed"}},
                    ],
                ),
                patch("tasks.intelligence_tasks.llm_text", return_value="Narrative summary"),
            ):
                result = document_ingestion_agent(state)

        report = result.get("document_ingestion_report", {})
        self.assertEqual(report.get("coverage_status"), "covered")
        self.assertEqual(len(report.get("attempted_files", [])), 2)
        self.assertEqual(len(report.get("successful_files", [])), 1)
        self.assertEqual(len(report.get("failed_files", [])), 1)
        self.assertTrue(result.get("document_ingestion_confirmed"))
        self.assertIn("Path Coverage", result.get("document_summary", ""))
        self.assertIn("Files With Extraction Errors", result.get("document_summary", ""))

    def test_document_ingestion_agent_skips_when_document_route_is_empty(self):
        state = {
            "user_query": "Classify inventoried files.",
            "current_objective": "Classify inventoried files.",
            "local_drive_handler_routes": {"document_ingestion_agent": []},
            "local_drive_files": ["/tmp/model.xlsx", "/tmp/photo.png"],
            "document_index_to_memory": False,
        }

        with (
            patch("tasks.a2a_agent_utils.record_work_note"),
            patch("tasks.intelligence_tasks.log_task_update"),
            patch("tasks.intelligence_tasks.write_text_file"),
            patch("tasks.intelligence_tasks._maybe_upsert_memory"),
            patch("tasks.intelligence_tasks.parse_documents") as parse_documents_mock,
            patch("tasks.intelligence_tasks.llm_text"),
        ):
            result = document_ingestion_agent(state)

        parse_documents_mock.assert_not_called()
        self.assertTrue(result.get("document_ingestion_skipped"))
        self.assertEqual(result.get("document_ingestion_skip_reason"), "no_document_routes")

    def test_ocr_agent_skips_without_image_paths(self):
        state = {
            "user_query": "Read scanned receipts.",
            "current_objective": "Read scanned receipts.",
        }

        with (
            patch("tasks.a2a_agent_utils.record_work_note"),
            patch("tasks.intelligence_tasks.log_task_update"),
            patch("tasks.intelligence_tasks.write_text_file"),
        ):
            result = ocr_agent(state)

        self.assertEqual(result.get("ocr_results"), [])
        self.assertTrue(result.get("ocr_skipped"))
        self.assertEqual(result.get("ocr_skip_reason"), "no_image_paths")
        self.assertIn("No image files were found for OCR", result.get("ocr_summary", ""))

    def test_ocr_agent_uses_local_drive_files_and_skips_failed_images(self):
        with TemporaryDirectory() as tmp:
            image_ok = os.path.join(tmp, "ok.png")
            image_bad = os.path.join(tmp, "bad.jpg")
            with open(image_ok, "wb") as handle:
                handle.write(b"fake")
            with open(image_bad, "wb") as handle:
                handle.write(b"fake")

            state = {
                "user_query": "Extract text from images.",
                "current_objective": "Extract text from images.",
                "local_drive_files": [image_ok, image_bad],
            }

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch(
                    "tasks.intelligence_tasks.openai_ocr_image",
                    side_effect=[
                        {"path": image_ok, "text": "Invoice 101", "raw": {"ok": True}},
                        RuntimeError("decode failed"),
                    ],
                ),
                patch("tasks.intelligence_tasks.llm_text", return_value="OCR summary"),
            ):
                result = ocr_agent(state)

        self.assertFalse(result.get("ocr_skipped"))
        self.assertEqual(len(result.get("ocr_results", [])), 2)
        self.assertEqual(len(result.get("ocr_successful_files", [])), 1)
        self.assertEqual(len(result.get("ocr_failed_files", [])), 1)
        self.assertIn("Skipped: 1", result.get("ocr_summary", ""))

    def test_local_drive_agent_routes_files_by_extension_and_requests_optional_handler_generation(self):
        with TemporaryDirectory() as tmp:
            txt_path = os.path.join(tmp, "notes.txt")
            excel_path = os.path.join(tmp, "model.xlsx")
            image_path = os.path.join(tmp, "photo.png")
            unknown_path = os.path.join(tmp, "ledger.abc")
            for path in (txt_path, excel_path, image_path, unknown_path):
                with open(path, "wb") as handle:
                    handle.write(b"sample")

            state = {
                "user_query": "Catalog files and route specialist handlers.",
                "current_objective": "Catalog files and route specialist handlers.",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_extensions": "txt,xlsx,png,abc",
                "local_drive_auto_generate_extension_handlers": True,
                "local_drive_index_to_memory": False,
            }

            def _fake_parse(paths, **_kwargs):
                path = paths[0]
                suffix = os.path.splitext(path)[1].lstrip(".") or "unknown"
                if path.endswith(".abc"):
                    return [{"path": path, "text": "", "metadata": {"type": suffix, "error": "unsupported"}}]
                return [{"path": path, "text": f"content for {suffix}", "metadata": {"type": suffix, "error": ""}}]

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch("tasks.intelligence_tasks.parse_documents", side_effect=_fake_parse),
                patch("tasks.intelligence_tasks.llm_text", return_value="summary"),
            ):
                result = local_drive_agent(state)

        routes = result.get("local_drive_handler_routes", {})
        self.assertIn("document_ingestion_agent", routes)
        self.assertIn("excel_agent", routes)
        self.assertIn("ocr_agent", routes)
        self.assertIn(txt_path, routes["document_ingestion_agent"])
        self.assertIn(unknown_path, routes["document_ingestion_agent"])
        self.assertIn(excel_path, routes["excel_agent"])
        self.assertIn(image_path, routes["ocr_agent"])
        self.assertIn(".abc", result.get("local_drive_unknown_extensions", []))
        self.assertTrue(result.get("extension_handler_generation_requested"))
        self.assertFalse(result.get("extension_handler_generation_dispatched"))
        self.assertIn(".abc", result.get("missing_capability", ""))
        self.assertIn(unknown_path, result.get("document_paths", []))
        self.assertIn(image_path, result.get("ocr_image_paths", []))
        self.assertIn(excel_path, result.get("excel_file_paths", []))

    def test_local_drive_agent_duplicate_filename_mode_skips_document_parsing(self):
        with TemporaryDirectory() as tmp:
            folder_a = os.path.join(tmp, "a")
            folder_b = os.path.join(tmp, "b")
            os.makedirs(folder_a, exist_ok=True)
            os.makedirs(folder_b, exist_ok=True)
            path_a = os.path.join(folder_a, "report.txt")
            path_b = os.path.join(folder_b, "report.txt")
            with open(path_a, "w", encoding="utf-8") as handle:
                handle.write("one")
            with open(path_b, "w", encoding="utf-8") as handle:
                handle.write("two")

            state = {
                "user_query": "identify duplicate files with same name",
                "current_objective": "identify duplicate files with same name in D drive",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_index_to_memory": False,
            }

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks.parse_documents") as parse_documents_mock,
                patch("tasks.intelligence_tasks.llm_text") as llm_text_mock,
            ):
                result = local_drive_agent(state)

        parse_documents_mock.assert_not_called()
        llm_text_mock.assert_not_called()
        self.assertIn("Duplicate Filename Report", result["draft_response"])
        self.assertIn("report.txt (2)", result["draft_response"])
        duplicate_groups = result.get("local_drive_duplicate_name_groups", [])
        self.assertEqual(len(duplicate_groups), 1)
        self.assertEqual(duplicate_groups[0]["name"], "report.txt")
        self.assertEqual(duplicate_groups[0]["count"], 2)

    def test_local_drive_agent_prioritizes_business_documents_over_package_noise(self):
        with TemporaryDirectory() as tmp:
            paths = {
                "package": os.path.join(tmp, "package.txt"),
                "readme": os.path.join(tmp, "readme.txt"),
                "pdf": os.path.join(tmp, "aws-chaos-architecture.pdf"),
                "pptx": os.path.join(tmp, "failure-simulation.pptx"),
            }
            for path in paths.values():
                with open(path, "wb") as handle:
                    handle.write(b"sample")

            state = {
                "user_query": "Research chaos engineering failure simulation on AWS from local files.",
                "current_objective": "Research chaos engineering failure simulation on AWS from local files.",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_max_files": 2,
                "local_drive_index_to_memory": False,
            }

            def _fake_parse(selected_paths, **_kwargs):
                path = selected_paths[0]
                suffix = os.path.splitext(path)[1].lstrip(".") or "unknown"
                return [{"path": path, "text": f"content for {suffix}", "metadata": {"type": suffix, "error": ""}}]

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch("tasks.intelligence_tasks.parse_documents", side_effect=_fake_parse),
                patch("tasks.intelligence_tasks.llm_text", side_effect=["doc summary", "doc summary", "rollup"]),
            ):
                result = local_drive_agent(state)

        self.assertEqual(len(result.get("local_drive_files", [])), 2)
        self.assertIn(paths["pdf"], result["local_drive_files"])
        self.assertIn(paths["pptx"], result["local_drive_files"])
        self.assertNotIn(paths["package"], result["local_drive_files"])
        self.assertNotIn(paths["readme"], result["local_drive_files"])
        self.assertIn("deep_research_source_strategy", result)
        self.assertIn("deep_research_intent", result)
        self.assertTrue(result["local_drive_manifest"]["source_strategy"])
        selected_entries = [
            item for item in result["local_drive_manifest"]["files"]
            if item.get("selected_for_processing")
        ]
        self.assertTrue(all(item.get("selection_reason") for item in selected_entries))
        skipped_entries = [
            item for item in result["local_drive_manifest"]["files"]
            if not item.get("selected_for_processing") and item.get("exclusion_reason")
        ]
        self.assertTrue(any(item.get("skip_reason_detail") for item in skipped_entries))

    def test_local_drive_agent_prioritizes_code_files_for_code_objectives(self):
        with TemporaryDirectory() as tmp:
            paths = {
                "docx": os.path.join(tmp, "strategy.docx"),
                "pdf": os.path.join(tmp, "overview.pdf"),
                "py": os.path.join(tmp, "service.py"),
                "ts": os.path.join(tmp, "api.ts"),
            }
            for path in paths.values():
                with open(path, "wb") as handle:
                    handle.write(b"sample")

            state = {
                "user_query": "Analyze the repository source code and architecture from local files.",
                "current_objective": "Analyze the repository source code and architecture from local files.",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_max_files": 2,
                "local_drive_index_to_memory": False,
            }

            def _fake_parse(selected_paths, **_kwargs):
                path = selected_paths[0]
                suffix = os.path.splitext(path)[1].lstrip(".") or "unknown"
                return [{"path": path, "text": f"content for {suffix}", "metadata": {"type": suffix, "error": ""}}]

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch("tasks.intelligence_tasks.parse_documents", side_effect=_fake_parse),
                patch("tasks.intelligence_tasks.llm_text", side_effect=["doc summary", "doc summary", "rollup"]),
            ):
                result = local_drive_agent(state)

        self.assertEqual(len(result.get("local_drive_files", [])), 2)
        self.assertIn(paths["py"], result["local_drive_files"])
        self.assertIn(paths["ts"], result["local_drive_files"])
        self.assertNotIn(paths["docx"], result["local_drive_files"])
        self.assertNotIn(paths["pdf"], result["local_drive_files"])

    def test_local_drive_agent_skips_generated_artifacts_in_favor_of_primary_documents(self):
        with TemporaryDirectory() as tmp:
            paths = {
                "log": os.path.join(tmp, "execution.log"),
                "notes": os.path.join(tmp, "agent_work_notes.txt"),
                "summary": os.path.join(tmp, "executive-summary.docx"),
                "architecture": os.path.join(tmp, "architecture-overview.pdf"),
            }
            for path in paths.values():
                with open(path, "wb") as handle:
                    handle.write(b"sample")

            state = {
                "user_query": "Research the AWS failure architecture and summarize the main findings from local files.",
                "current_objective": "Research the AWS failure architecture and summarize the main findings from local files.",
                "local_drive_paths": [tmp],
                "local_drive_working_directory": tmp,
                "local_drive_max_files": 2,
                "local_drive_index_to_memory": False,
            }

            def _fake_parse(selected_paths, **_kwargs):
                path = selected_paths[0]
                suffix = os.path.splitext(path)[1].lstrip(".") or "unknown"
                return [{"path": path, "text": f"content for {suffix}", "metadata": {"type": suffix, "error": ""}}]

            with (
                patch("tasks.a2a_agent_utils.record_work_note"),
                patch("tasks.intelligence_tasks.log_task_update"),
                patch("tasks.intelligence_tasks.write_text_file"),
                patch("tasks.intelligence_tasks._maybe_upsert_memory"),
                patch("tasks.intelligence_tasks.parse_documents", side_effect=_fake_parse),
                patch("tasks.intelligence_tasks.llm_text", side_effect=["doc summary", "doc summary", "rollup"]),
            ):
                result = local_drive_agent(state)

        self.assertEqual(result.get("local_drive_files", []), [paths["architecture"], paths["summary"]])
        manifest_files = result["local_drive_manifest"]["files"]
        selected_entries = [item for item in manifest_files if item.get("selected_for_processing")]
        skipped_entries = {item["path"]: item for item in manifest_files if not item.get("selected_for_processing")}
        self.assertTrue(any(item.get("priority_boosts") for item in selected_entries))
        self.assertIn("generated research artifact", skipped_entries[paths["log"]].get("skip_reason_detail", ""))
        self.assertIn("generated research artifact", skipped_entries[paths["notes"]].get("skip_reason_detail", ""))


if __name__ == "__main__":
    unittest.main()
