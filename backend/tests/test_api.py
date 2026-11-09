"""
Backend tests that don't call any AI provider.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import json
import _testenv  # noqa: F401  (must come before app imports)
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from providers import provider_router  # noqa: E402
from services import panel_engine  # noqa: E402
from services.errors import AIServiceError  # noqa: E402
from services.expert_manager import expert_manager  # noqa: E402

PANEL_SYNTHESIS = json.dumps({
    "agreements": "a", "disagreements": "d", "top_priorities": "t",
    "risks": "r", "recommended_next_steps": "n", "panel_verdict": "v",
})


class ValidationTests(unittest.TestCase):

    def setUp(self):
        self.client = _testenv.client(app)

    def test_non_json_body_is_a_400_not_a_500(self):
        res = self.client.post("/panel", data="x", content_type="text/plain")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_panel_requires_experts(self):
        res = self.client.post("/panel", json={"problem": "x", "experts": []})
        self.assertEqual(res.status_code, 400)

    def test_unknown_route_returns_json_404(self):
        res = self.client.get("/does-not-exist")
        self.assertEqual(res.status_code, 404)
        self.assertIn("error", res.get_json())

    def test_discovery_has_steps_for_every_expert(self):
        for key in expert_manager.get_all_experts():
            res = self.client.post("/expert/discovery", json={"expert": key})
            steps = res.get_json()["steps"]
            self.assertEqual(len(steps), 3, key)
            names = [f["name"] for f in steps[0]["fields"]]
            self.assertIn("description", names, key)

    def test_recommend_rejects_unknown_expert(self):
        res = self.client.post("/expert/recommend", json={"expert": "Nobody", "answers": {}})
        self.assertEqual(res.status_code, 404)

    def test_unexpected_errors_do_not_leak_details(self):
        with mock.patch("app.run_panel", side_effect=RuntimeError("secret internals")):
            res = self.client.post("/panel", json={"problem": "x", "experts": ["Software Architect"]})
        self.assertEqual(res.status_code, 500)
        self.assertNotIn("secret", res.get_json()["error"])


class ExpertMatchingTests(unittest.TestCase):

    def test_substrings_do_not_trigger_an_expert_switch(self):
        for message in [
            "How should I build the API layer?",
            "What are the main requirements?",
            "Can you give a quick summary?",
        ]:
            self.assertIsNone(expert_manager.find_manual_request(message), message)

    def test_explicit_requests_still_switch(self):
        self.assertEqual(expert_manager.find_manual_request("Can Alex join?"), "Database Engineer")
        self.assertEqual(expert_manager.find_manual_request("Ask Maya about the UI"), "Design Advisor")

    def test_match_endpoint(self):
        client = _testenv.client(app)
        res = client.post("/expert/match", json={"problem": "Design a postgres schema with indexing"})
        body = res.get_json()
        self.assertEqual(body["expert_key"], "Database Engineer")
        self.assertIn("schema", body["matched"])

        res = client.post("/expert/match", json={"problem": "Hello"})
        self.assertEqual(res.get_json()["expert_key"], "Software Architect")
        self.assertEqual(res.get_json()["matched"], [])


class PanelTests(unittest.TestCase):

    def setUp(self):
        self.client = _testenv.client(app)

    def _panel(self, experts):
        return self.client.post("/panel", json={"problem": "Build a SaaS app", "experts": experts})

    def test_partial_failure_keeps_successful_responses(self):
        def fake_generate(prompt, **kwargs):
            if "Sarah Patel" in prompt:
                raise AIServiceError("All providers down.")
            if "Panel Coordinator" in prompt:
                return PANEL_SYNTHESIS
            return "## Assessment\nLooks good."

        with mock.patch.object(panel_engine, "generate", side_effect=fake_generate):
            body = self._panel(["Software Architect", "Security Expert", "Database Engineer"]).get_json()

        statuses = {r["expert_key"]: r["status"] for r in body["responses"]}
        self.assertEqual(statuses, {
            "Software Architect": "success",
            "Security Expert": "error",
            "Database Engineer": "success",
        })
        self.assertEqual([r["expert_key"] for r in body["responses"]],
                         ["Software Architect", "Security Expert", "Database Engineer"])
        self.assertEqual(body["synthesis"]["panel_verdict"], "v")
        self.assertIsNone(body["synthesis_error"])

    def test_synthesis_failure_is_reported_not_faked(self):
        def fake_generate(prompt, **kwargs):
            if "Panel Coordinator" in prompt:
                return "not json"
            return "## Assessment\nOK"

        with mock.patch.object(panel_engine, "generate", side_effect=fake_generate):
            body = self._panel(["Software Architect", "Cloud Consultant"]).get_json()

        self.assertEqual(body["successful_count"], 2)
        self.assertIsNone(body["synthesis"])
        self.assertTrue(body["synthesis_error"])

    def test_slow_expert_times_out_without_losing_others(self):
        def fake_generate(prompt, **kwargs):
            if "Daniel Brooks" in prompt:
                time.sleep(2)
            return "## Assessment\nOK"

        with mock.patch.object(panel_engine, "generate", side_effect=fake_generate), \
                mock.patch.object(panel_engine, "_EXPERT_TIMEOUT", 0.5):
            body = self._panel(["Software Architect", "Cloud Consultant"]).get_json()

        statuses = {r["expert_key"]: r["status"] for r in body["responses"]}
        self.assertEqual(statuses["Software Architect"], "success")
        self.assertEqual(statuses["Cloud Consultant"], "error")


class ProviderRouterTests(unittest.TestCase):

    def _router_with(self, *generators):
        router = provider_router.ProviderRouter()
        router.providers = [
            {"name": f"P{i}", "generate": g, "enabled": True}
            for i, g in enumerate(generators)
        ]
        return router

    def test_falls_back_to_next_provider(self):
        def fail(*a, **k):
            raise Exception("503 service unavailable")

        router = self._router_with(fail, lambda *a, **k: "hello")
        self.assertEqual(router.generate("hi"), "hello")

    def test_all_failures_raise_user_safe_error(self):
        def fail(*a, **k):
            raise Exception("Connection refused at 10.0.0.1")

        with self.assertRaises(AIServiceError) as ctx:
            self._router_with(fail, fail).generate("hi")
        self.assertNotIn("10.0.0.1", str(ctx.exception))

    def test_account_limit_is_reported_from_status_code(self):
        from services.errors import ProviderError, ACCOUNT_LIMIT

        def quota(*a, **k):
            raise ProviderError(ACCOUNT_LIMIT, "429 free-models-per-day")

        with self.assertRaises(AIServiceError) as ctx:
            self._router_with(quota).generate("hi")
        self.assertEqual(ctx.exception.category, ACCOUNT_LIMIT)
        self.assertIn("usage limit", str(ctx.exception))

    def test_unrelated_text_is_not_misreported_as_key_problem(self):
        # The old phrase matching blamed the API key for any error mentioning it.
        def fail(*a, **k):
            raise Exception("connect failed while sending api_key header")

        with self.assertRaises(AIServiceError) as ctx:
            self._router_with(fail).generate("hi")
        self.assertNotIn("API key", str(ctx.exception))

    def test_ai_errors_become_503_responses(self):
        client = _testenv.client(app)
        with mock.patch("app.analyze_project", side_effect=AIServiceError("AI down, try later.")):
            res = client.post("/analyze", json={"prompt": "A project"})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.get_json()["error"], "AI down, try later.")


if __name__ == "__main__":
    unittest.main()
