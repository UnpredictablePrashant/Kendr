import os
import tempfile
import unittest

from kendr.persistence import (
    claim_plan_task,
    initialize_db,
    insert_orchestration_event,
    list_execution_plans,
    list_intent_candidates,
    list_orchestration_events,
    list_recent_orchestration_events,
    list_plan_tasks,
    list_task_dependencies,
    release_plan_task_lease,
    replace_intent_candidates,
    replace_plan_tasks,
    update_execution_plan_status,
    update_plan_task_state,
    upsert_execution_plan,
)


class OrchestrationStoreTests(unittest.TestCase):
    def test_orchestration_store_persists_intents_plans_steps_and_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "workflow.sqlite3")
            initialize_db(db_path)

            replace_intent_candidates(
                "run-1",
                [
                    {
                        "intent_id": "intent-general",
                        "intent_type": "general_task",
                        "label": "General task workflow",
                        "score": 60,
                        "selected": False,
                        "execution_mode": "adaptive",
                        "requires_planner": False,
                        "risk_level": "low",
                        "reasons": ["fallback intent"],
                        "metadata": {"planner_score": 2},
                    },
                    {
                        "intent_id": "intent-project",
                        "intent_type": "project_build",
                        "label": "Project build workflow",
                        "score": 92,
                        "selected": True,
                        "execution_mode": "plan",
                        "requires_planner": True,
                        "risk_level": "medium",
                        "reasons": ["project build detected"],
                        "metadata": {"workflow": "project_build"},
                    },
                ],
                objective_signature="abc123",
                db_path=db_path,
            )
            plan = upsert_execution_plan(
                "run-1:plan:v1",
                run_id="run-1",
                intent_id="intent-project",
                version=1,
                status="awaiting_approval",
                approval_status="pending",
                objective="Build the project",
                summary="Initial execution plan",
                plan_markdown="# Plan",
                plan_data={"summary": "Initial execution plan"},
                metadata={"source": "test"},
                db_path=db_path,
            )
            replace_plan_tasks(
                plan["plan_id"],
                "run-1",
                [
                    {
                        "id": "step-1",
                        "title": "Scaffold project",
                        "agent": "worker_agent",
                        "task": "Scaffold the project.",
                        "success_criteria": "Project structure exists.",
                    },
                    {
                        "id": "step-2",
                        "title": "Run checks",
                        "agent": "worker_agent",
                        "task": "Run the project checks.",
                        "depends_on": ["step-1"],
                        "success_criteria": "Checks pass.",
                    },
                ],
                db_path=db_path,
            )
            update_execution_plan_status(
                plan["plan_id"],
                status="executing",
                approval_status="approved",
                db_path=db_path,
            )
            update_plan_task_state(
                plan["plan_id"],
                "step-1",
                status="completed",
                completed_at="2026-04-15T00:00:00+00:00",
                result_summary="Project scaffold created.",
                db_path=db_path,
            )
            insert_orchestration_event(
                {
                    "run_id": "run-1",
                    "plan_id": plan["plan_id"],
                    "subject_type": "plan_task",
                    "subject_id": "step-1",
                    "event_type": "plan_task.completed",
                    "status": "completed",
                    "source": "test",
                    "payload": {"result_summary": "Project scaffold created."},
                },
                db_path=db_path,
            )

            intents = list_intent_candidates("run-1", objective_signature="abc123", db_path=db_path)
            plans = list_execution_plans("run-1", db_path=db_path)
            steps = list_plan_tasks(plan_id=plan["plan_id"], db_path=db_path)
            deps = list_task_dependencies(plan["plan_id"], db_path=db_path)
            events = list_orchestration_events("run-1", db_path=db_path)
            recent_events = list_recent_orchestration_events(limit=10, db_path=db_path)

            self.assertEqual(len(intents), 2)
            self.assertEqual(intents[0]["intent_id"], "intent-project")
            self.assertTrue(intents[0]["selected"])
            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0]["status"], "executing")
            self.assertEqual(plans[0]["approval_status"], "approved")
            self.assertEqual(len(steps), 2)
            self.assertEqual(steps[0]["status"], "completed")
            self.assertEqual(steps[0]["result_summary"], "Project scaffold created.")
            self.assertEqual(len(deps), 1)
            self.assertEqual(deps[0]["depends_on_step_id"], "step-1")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "plan_task.completed")
            self.assertEqual(len(recent_events), 1)
            self.assertEqual(recent_events[0]["subject_id"], "step-1")

    def test_plan_task_leases_can_be_claimed_and_released(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "workflow.sqlite3")
            initialize_db(db_path)
            plan = upsert_execution_plan(
                "run-lease:plan:v1",
                run_id="run-lease",
                version=1,
                status="approved",
                approval_status="approved",
                objective="Inspect local files",
                summary="Lease test",
                db_path=db_path,
            )
            replace_plan_tasks(
                plan["plan_id"],
                "run-lease",
                [
                    {
                        "id": "step-1",
                        "title": "Catalog files",
                        "agent": "local_drive_agent",
                        "task": "Catalog the files.",
                        "success_criteria": "A file inventory exists.",
                        "side_effect_level": "read_only",
                        "conflict_keys": ["agent:local_drive_agent"],
                    }
                ],
                db_path=db_path,
            )

            first_claim = claim_plan_task(plan["plan_id"], "step-1", lease_owner="worker-1", db_path=db_path)
            second_claim = claim_plan_task(plan["plan_id"], "step-1", lease_owner="worker-2", db_path=db_path)
            release_plan_task_lease(plan["plan_id"], "step-1", lease_owner="worker-1", db_path=db_path)
            third_claim = claim_plan_task(plan["plan_id"], "step-1", lease_owner="worker-2", db_path=db_path)

            self.assertIsNotNone(first_claim)
            self.assertIsNone(second_claim)
            self.assertIsNotNone(third_claim)
            self.assertEqual(third_claim["lease_owner"], "worker-2")
            self.assertEqual(int(third_claim["attempt_count"]), 2)


if __name__ == "__main__":
    unittest.main()
