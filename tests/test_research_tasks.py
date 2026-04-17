import os
import unittest
from unittest.mock import MagicMock, patch


os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")


class _FakeResponse:
    def __init__(self, *, response_id: str, status: str, output_text: str):
        self.id = response_id
        self.status = status
        self.output_text = output_text

    def model_dump(self):
        return {"id": self.id, "status": self.status, "output_text": self.output_text}


class DeepResearchAgentTests(unittest.TestCase):
    def test_deep_research_agent_injects_kb_grounding_into_web_research(self):
        from tasks import research_tasks

        captured = {}
        fake_client = MagicMock()

        def _create(**kwargs):
            captured.update(kwargs)
            return _FakeResponse(response_id="resp-1", status="completed", output_text="grounded answer")

        fake_client.responses.create.side_effect = _create

        state = {
            "user_query": "Analyze the market structure",
            "research_kb_enabled": True,
            "research_web_search_enabled": True,
        }

        with (
            patch("tasks.research_tasks.begin_agent_session", return_value=(None, "", None)),
            patch("tasks.research_tasks.OpenAI", return_value=fake_client),
            patch(
                "tasks.research_tasks.build_research_grounding",
                return_value={
                    "kb_id": "kb-1",
                    "kb_name": "finance-kb",
                    "prompt_context": "Knowledge Base Grounding:\n- KB: finance-kb",
                    "hit_count": 2,
                    "citations": [{"source_id": "file:///tmp/report.md"}],
                },
            ),
            patch("tasks.research_tasks.write_text_file"),
            patch("tasks.research_tasks.publish_agent_output", side_effect=lambda state, *args, **kwargs: state),
        ):
            result = research_tasks.deep_research_agent(state)

        self.assertIn("Knowledge Base Grounding", captured["instructions"])
        self.assertTrue(result["research_kb_used"])
        self.assertEqual(result["research_kb_name"], "finance-kb")
        self.assertEqual(result["research_kb_hit_count"], 2)
        self.assertIn("Deep Research Brief", result["research_result"])
        self.assertIn("Coverage:", result["research_result"])
        self.assertIn("Sources:", result["research_result"])
        self.assertIn("Knowledge base: finance-kb (2 hits)", result["research_result"])
        self.assertIn("KB source: file:///tmp/report.md", result["research_result"])
        self.assertIn("Recommended Next Steps:", result["research_result"])
        self.assertIn("Knowledge base: finance-kb (2 hits)", result["research_source_summary"][0])
        self.assertEqual(result["deep_research_result_card"]["kind"], "brief")
        self.assertTrue(result["deep_research_result_card"]["web_search_enabled"])

    def test_deep_research_agent_rejects_kb_only_run_when_kb_fails(self):
        from tasks import research_tasks

        state = {
            "user_query": "Analyze the market structure",
            "research_kb_enabled": True,
            "research_web_search_enabled": False,
        }

        with (
            patch("tasks.research_tasks.begin_agent_session", return_value=(None, "", None)),
            patch("tasks.research_tasks.build_research_grounding", side_effect=ValueError("Knowledge base is not indexed yet.")),
        ):
            with self.assertRaises(ValueError) as exc:
                research_tasks.deep_research_agent(state)

        self.assertIn("no other evidence sources", str(exc.exception).lower())

    def test_deep_research_agent_supports_local_only_with_kb_and_explicit_urls(self):
        from tasks import research_tasks

        state = {
            "user_query": "Analyze the market structure",
            "research_kb_enabled": True,
            "research_web_search_enabled": False,
            "deep_research_source_urls": ["https://example.com/report"],
        }

        with (
            patch("tasks.research_tasks.begin_agent_session", return_value=(None, "", None)),
            patch(
                "tasks.research_tasks.build_research_grounding",
                return_value={
                    "kb_id": "kb-1",
                    "kb_name": "finance-kb",
                    "prompt_context": "Knowledge Base Grounding:\n- KB: finance-kb",
                    "hit_count": 1,
                    "citations": [{"source_id": "file:///tmp/report.md"}],
                },
            ),
            patch("tasks.research_tasks.fetch_url_content", return_value={"text": "Explicit URL evidence", "content_type": "text/html"}),
            patch("tasks.research_tasks.llm_text", return_value="local memo"),
            patch("tasks.research_tasks.write_text_file"),
            patch("tasks.research_tasks.publish_agent_output", side_effect=lambda state, *args, **kwargs: state),
        ):
            result = research_tasks.deep_research_agent(state)

        self.assertEqual(result["research_status"], "completed")
        self.assertTrue(result["research_kb_used"])
        self.assertEqual(result["research_kb_hit_count"], 1)
        self.assertEqual(result["research_raw"]["provided_url_count"], 1)
        self.assertIn("Deep Research Brief", result["research_result"])
        self.assertIn("Coverage:", result["research_result"])
        self.assertIn("Sources:", result["research_result"])
        self.assertIn("Knowledge base: finance-kb (1 hit)", result["research_result"])
        self.assertIn("Provided URL: https://example.com/report", result["research_result"])
        self.assertIn("Recommended Next Steps:", result["research_result"])
        self.assertIn("- Provided URL: https://example.com/report", result["research_source_summary"])
        self.assertEqual(result["deep_research_result_card"]["mode"], "local_only")
