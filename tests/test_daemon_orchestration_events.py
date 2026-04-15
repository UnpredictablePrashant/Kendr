import os
import tempfile
import unittest
from unittest.mock import patch

from kendr.daemon import _process_orchestration_events
from kendr.persistence import initialize_db, insert_orchestration_event


class DaemonOrchestrationEventTests(unittest.TestCase):
    def test_process_orchestration_events_logs_relevant_runtime_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "workflow.sqlite3")
            initialize_db(db_path)
            insert_orchestration_event(
                {
                    "event_id": "evt-1",
                    "run_id": "run-1",
                    "subject_type": "run",
                    "subject_id": "run-1",
                    "event_type": "run.completed",
                    "status": "completed",
                    "timestamp": "2026-04-15T00:00:00+00:00",
                    "payload": {"final_output_excerpt": "Finished successfully."},
                },
                db_path=db_path,
            )

            with patch("kendr.daemon.log_task_update") as log_update:
                cursor = _process_orchestration_events("", db_path=db_path)

            self.assertEqual(cursor, "2026-04-15T00:00:00+00:00")
            log_update.assert_called()
            self.assertIn("run.completed", log_update.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
