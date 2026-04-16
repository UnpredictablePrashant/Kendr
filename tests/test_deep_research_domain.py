import unittest

from kendr.domain.deep_research import build_source_strategy, discover_research_intent


class DeepResearchDomainTests(unittest.TestCase):
    def test_discover_research_intent_prefers_docs_for_market_research(self):
        intent = discover_research_intent("Create a diligence report on the cloud backup market from local files and web sources.")

        self.assertEqual(intent["research_kind"], "mixed")
        self.assertEqual(intent["target_deliverable"], "diligence pack")
        self.assertIn("local docs", intent["source_needs"])
        self.assertIn("web", intent["source_needs"])
        self.assertTrue(intent["docs_first"])
        self.assertIn("mutate_repo", intent["banned_actions"])

    def test_build_source_strategy_allocates_doc_heavy_budget(self):
        intent = discover_research_intent("Research AWS failure simulation from PDF, PPTX, and spreadsheet files.")

        strategy = build_source_strategy(
            intent,
            max_files=120,
            allow_web_search=True,
            local_paths_present=True,
        )

        budgets = strategy["family_budgets"]
        self.assertGreater(budgets["document"], budgets["code"])
        self.assertGreater(budgets["presentation"], 0)
        self.assertGreater(budgets["spreadsheet"], 0)
        self.assertTrue(strategy["web_search_needed"])


if __name__ == "__main__":
    unittest.main()
