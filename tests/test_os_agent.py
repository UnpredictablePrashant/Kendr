import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from tasks.os_tasks import os_agent


class OsAgentTests(unittest.TestCase):
    def test_policy_blocked_command_still_publishes_execution_report(self):
        with TemporaryDirectory() as tmp:
            state = {
                "user_query": "Run a local command.",
                "os_command": "rm -rf temp-output",
                "working_directory": tmp,
            }

            with (
                patch("tasks.os_tasks.begin_agent_session", return_value=(None, state["user_query"], "orchestrator_agent")),
                patch("tasks.os_tasks.publish_agent_output", side_effect=lambda current_state, *_args, **_kwargs: current_state),
                patch("tasks.os_tasks.write_text_file"),
                patch("tasks.os_tasks.log_task_update"),
                patch("tasks.os_tasks.append_privileged_audit_event"),
            ):
                result = os_agent(state)

        self.assertFalse(result["os_success"])
        self.assertIsNone(result["os_return_code"])
        self.assertIn("policy_blocked", result["draft_response"])
        self.assertIn("Thought:", result["draft_response"])
        self.assertIn("Mutating:", result["draft_response"])


if __name__ == "__main__":
    unittest.main()
