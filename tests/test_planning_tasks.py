import os
import unittest

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from tasks.planning_tasks import normalize_plan_data


class PlanningTaskTests(unittest.TestCase):
    def test_normalize_plan_data_excludes_planner_from_execution_steps(self):
        raw_plan = {
            "summary": "Test plan",
            "steps": [
                {
                    "id": "step-1",
                    "title": "Lock scope",
                    "agent": "planner_agent",
                    "task": "Refine the scope note.",
                    "substeps": [
                        {
                            "id": "step-1.1",
                            "title": "List requirements",
                            "agent": "planner_agent",
                            "task": "List the report requirements.",
                        }
                    ],
                },
                {
                    "id": "step-2",
                    "title": "Catalog files",
                    "agent": "local_drive_agent",
                    "task": "Catalog the local files and summarize the usable evidence.",
                    "success_criteria": "A file catalog and evidence summary exist.",
                },
            ],
        }

        plan_data = normalize_plan_data(raw_plan, "Build a fundraising report.")

        self.assertEqual(len(plan_data["steps"]), 2)
        self.assertEqual(len(plan_data["execution_steps"]), 1)
        self.assertEqual(plan_data["execution_steps"][0]["id"], "step-2")
        self.assertEqual(plan_data["execution_steps"][0]["agent"], "local_drive_agent")


if __name__ == "__main__":
    unittest.main()
