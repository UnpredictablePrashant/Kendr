import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from tasks.intelligence_tasks import local_drive_agent


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
        self.assertIn("Rollup Findings", result["draft_response"])


if __name__ == "__main__":
    unittest.main()
