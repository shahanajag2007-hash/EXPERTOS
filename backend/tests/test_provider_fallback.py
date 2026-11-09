"""
Provider fallback across OpenRouter -> Gemini -> Groq -> Ollama.

The real provider modules are used; only their SDK calls are mocked, so the
classification of real SDK exception types is exercised. No network access.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import json
import sqlite3
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import groq
import httpx
import openai
from google.api_core import exceptions as google_exceptions

from app import app
import app as app_module
from providers import gemini_provider, groq_provider, provider_router
from services.errors import (
    AIServiceError, ProviderError, retry_at_from_exception,
    ACCOUNT_LIMIT, AUTH, CREDITS, EMPTY, MALFORMED, MODEL_NOT_FOUND, RATE_LIMIT, SERVER, TIMEOUT,
    CONNECTION,
)
from services.openrouter_client import AllModelsExhausted

OR_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
GROQ_REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


# ─── Fakes for each provider's SDK ───────────────────────────────────────────

def openrouter_daily_limit(reset_epoch):
    response = httpx.Response(
        429, request=OR_REQUEST,
        headers={"x-ratelimit-limit": "50", "x-ratelimit-remaining": "0",
                 "x-ratelimit-reset": str(int(reset_epoch * 1000))},
        json={"error": {"message": "Rate limit exceeded: free-models-per-day"}},
    )
    return openai.APIStatusError("Error code: 429 - Rate limit exceeded: free-models-per-day",
                                 response=response, body=None)


def gemini_daily_quota(retry_seconds=68982):
    return google_exceptions.TooManyRequests(
        "You exceeded your current quota, please check your plan and billing details.",
        details=[
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": f"{retry_seconds}s"},
        ],
    )


def gemini_response(text, reason="STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason))])


def groq_completion(text, finish="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish)])


def groq_error(status, message):
    response = httpx.Response(status, request=GROQ_REQUEST, json={"error": {"message": message}})
    cls = {404: groq.NotFoundError, 401: groq.AuthenticationError}.get(status, groq.APIStatusError)
    return cls(message, response=response, body=None)


class FallbackBase(unittest.TestCase):
    """A router wired to the real provider modules with mocked SDK calls."""

    def setUp(self):
        self.db_path = _testenv.fresh_database()
        self.router = provider_router.ProviderRouter()
        for p in self.router.providers:
            p["enabled"] = p["name"] in ("OpenRouter", "Gemini", "Groq")

        self.openrouter = mock.Mock(return_value=("openrouter answer", {"model": "nvidia/x:free", "attempts": 1}))
        self.router.providers[0]["generate_with_info"] = self.openrouter

        gemini_patch = mock.patch.object(gemini_provider.model, "generate_content",
                                         return_value=gemini_response("gemini answer"))
        self.gemini = gemini_patch.start()
        self.addCleanup(gemini_patch.stop)

        self.groq = mock.Mock(return_value=groq_completion("groq answer"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.groq)))
        groq_patch = mock.patch.object(groq_provider, "_get_client", return_value=client)
        groq_patch.start()
        self.addCleanup(groq_patch.stop)

    def ai_calls(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM ai_calls ORDER BY id")]
        finally:
            conn.close()

    def calls(self):
        return {"openrouter": self.openrouter.call_count, "gemini": self.gemini.call_count,
                "groq": self.groq.call_count}


class PrimaryProviderTests(FallbackBase):

    def test_primary_success_calls_nothing_else(self):
        self.assertEqual(self.router.generate("q", request_type="recommendation"), "openrouter answer")
        self.assertEqual(self.calls(), {"openrouter": 1, "gemini": 0, "groq": 0})
        call = self.ai_calls()[0]
        self.assertEqual((call["provider"], call["model"], call["success"]), ("OpenRouter", "nvidia/x:free", 1))

    def test_transient_failures_fall_back_without_cooling_the_primary(self):
        for category in (RATE_LIMIT, SERVER, TIMEOUT, EMPTY, MALFORMED, MODEL_NOT_FOUND):
            with self.subTest(category=category):
                self.router.reset_cooldowns()
                self.gemini.reset_mock()
                self.openrouter.side_effect = AllModelsExhausted(category, "x")
                self.assertEqual(self.router.generate("q"), "gemini answer")
                expected_cooldown = category == MODEL_NOT_FOUND
                self.assertEqual(bool(self.router._cooling("OpenRouter")), expected_cooldown)

    def test_daily_quota_is_distinguished_and_skipped_until_reset(self):
        reset = time.time() + 3600
        self.openrouter.side_effect = AllModelsExhausted(ACCOUNT_LIMIT, "free-models-per-day",
                                                         retry_at=retry_at_from_exception(openrouter_daily_limit(reset)))
        self.assertEqual(self.router.generate("q"), "gemini answer")

        until, category, retry_at = self.router._cooling("OpenRouter")
        self.assertEqual(category, ACCOUNT_LIMIT)
        self.assertAlmostEqual(until, reset, delta=1)

        # The next request doesn't call the exhausted provider at all.
        self.assertEqual(self.router.generate("q"), "gemini answer")
        self.assertEqual(self.openrouter.call_count, 1)

    def test_auth_and_credit_failures_fall_back_and_pause_the_primary(self):
        for category in (AUTH, CREDITS):
            with self.subTest(category=category):
                self.router.reset_cooldowns()
                self.openrouter.reset_mock()
                self.openrouter.side_effect = AllModelsExhausted(category, "x")
                self.assertEqual(self.router.generate("q"), "gemini answer")
                self.router.generate("q")
                self.assertEqual(self.openrouter.call_count, 1)

    def test_cooldown_expires_and_success_clears_it(self):
        self.router._start_cooldown("OpenRouter", AUTH, None)
        with self.router._lock:
            until, cat, ra = self.router._cooldowns["OpenRouter"]
            self.router._cooldowns["OpenRouter"] = (time.time() - 1, cat, ra)
        self.assertEqual(self.router.generate("q"), "openrouter answer")
        self.assertIsNone(self.router._cooling("OpenRouter"))


class GeminiFallbackTests(FallbackBase):

    def setUp(self):
        super().setUp()
        self.openrouter.side_effect = AllModelsExhausted(RATE_LIMIT, "busy")

    def test_gemini_answers_after_primary_rate_limit_and_is_recorded(self):
        self.assertEqual(self.router.generate("q", request_type="recommendation", expert_key="Database Engineer"),
                         "gemini answer")
        call = self.ai_calls()[0]
        self.assertEqual((call["provider"], call["model"], call["success"]), ("Gemini", "gemini-2.5-flash", 1))
        attempts = json.loads(call["provider_attempts"])
        self.assertEqual([(a["provider"], a["category"]) for a in attempts],
                         [("OpenRouter", RATE_LIMIT), ("Gemini", None)])

    def test_gemini_daily_quota_uses_retry_delay(self):
        self.gemini.side_effect = gemini_daily_quota(68982)
        self.assertEqual(self.router.generate("q"), "groq answer")
        until, category, _ = self.router._cooling("Gemini")
        self.assertEqual(category, ACCOUNT_LIMIT)
        self.assertAlmostEqual(until, time.time() + 68982, delta=5)

    def test_gemini_auth_failure(self):
        self.gemini.side_effect = google_exceptions.BadRequest("API key not valid. Please pass a valid API key.")
        self.assertEqual(self.router.generate("q"), "groq answer")
        self.assertEqual(self.router._cooling("Gemini")[1], AUTH)

    def test_gemini_empty_and_truncated_answers_are_rejected(self):
        for response in (gemini_response("   "), gemini_response("When a user attempts to", "MAX_TOKENS")):
            with self.subTest(response=response.text):
                self.router.reset_cooldowns()
                self.gemini.return_value = response
                self.assertEqual(self.router.generate("q"), "groq answer")
                self.assertIsNone(self.router._cooling("Gemini"))   # transient, not paused

    def test_all_fallbacks_failing_gives_a_clear_error(self):
        self.gemini.side_effect = gemini_daily_quota()
        self.groq.side_effect = groq_error(404, "The model `llama-3.3-70b-versatile` does not exist")
        with self.assertRaises(AIServiceError) as ctx:
            self.router.generate("q")
        err = ctx.exception
        self.assertEqual(err.category, RATE_LIMIT)
        self.assertIn("backup AI providers couldn't complete the request", str(err))
        self.assertEqual([(a["provider"], a["category"]) for a in err.attempts],
                         [("OpenRouter", RATE_LIMIT), ("Gemini", ACCOUNT_LIMIT), ("Groq", MODEL_NOT_FOUND)])


class GroqTests(FallbackBase):

    def setUp(self):
        super().setUp()
        self.openrouter.side_effect = AllModelsExhausted(RATE_LIMIT, "busy")
        self.gemini.side_effect = gemini_daily_quota()

    def test_groq_answers_with_configured_model(self):
        self.assertEqual(self.router.generate("q", max_tokens=400), "groq answer")
        kwargs = self.groq.call_args.kwargs
        self.assertEqual(kwargs["model"], groq_provider.MODEL)
        self.assertEqual(kwargs["max_tokens"], 400 + groq_provider.REASONING_HEADROOM)
        self.assertEqual(self.ai_calls()[0]["provider"], "Groq")

    def test_invalid_groq_model_is_classified_and_paused(self):
        self.groq.side_effect = groq_error(404, "The model does not exist or you do not have access to it.")
        with self.assertRaises(AIServiceError):
            self.router.generate("q")
        self.assertEqual(self.router._cooling("Groq")[1], MODEL_NOT_FOUND)
        with self.assertRaises(AIServiceError):
            self.router.generate("q")
        self.assertEqual(self.groq.call_count, 1)   # not called again while paused

    def test_groq_unavailable(self):
        self.groq.side_effect = groq.APIConnectionError(request=GROQ_REQUEST)
        with self.assertRaises(AIServiceError) as ctx:
            self.router.generate("q")
        self.assertEqual(ctx.exception.attempts[-1]["category"], CONNECTION)

    def test_groq_truncated_or_empty_answer_rejected(self):
        for completion in (groq_completion("Because an index", "length"), groq_completion("")):
            with self.subTest(finish=completion.choices[0].finish_reason):
                self.groq.return_value = completion
                with self.assertRaises(AIServiceError) as ctx:
                    self.router.generate("q")
                self.assertEqual(ctx.exception.attempts[-1]["category"], EMPTY)

    def test_disabled_groq_is_never_called(self):
        self.router.providers[2]["enabled"] = False
        with self.assertRaises(AIServiceError) as ctx:
            self.router.generate("q")
        self.assertEqual(self.groq.call_count, 0)
        self.assertEqual([a["provider"] for a in ctx.exception.attempts], ["OpenRouter", "Gemini"])


class RoutingTests(FallbackBase):

    def test_order_and_no_duplicate_calls(self):
        order = []
        self.openrouter.side_effect = lambda *a, **k: order.append("OpenRouter") or (_ for _ in ()).throw(
            AllModelsExhausted(RATE_LIMIT, "busy"))
        self.gemini.side_effect = lambda *a, **k: order.append("Gemini") or (_ for _ in ()).throw(gemini_daily_quota())
        self.groq.side_effect = lambda *a, **k: order.append("Groq") or groq_completion("groq answer")
        self.assertEqual(self.router.generate("q"), "groq answer")
        self.assertEqual(order, ["OpenRouter", "Gemini", "Groq"])

    def test_every_provider_exhausted_fails_fast_without_requests(self):
        reset = time.time() + 7200
        self.openrouter.side_effect = AllModelsExhausted(ACCOUNT_LIMIT, "daily", retry_at=reset)
        self.gemini.side_effect = gemini_daily_quota(30000)
        self.groq.side_effect = groq_error(429, "Rate limit reached: tokens per day (TPD) quota")
        with self.assertRaises(AIServiceError) as first:
            self.router.generate("q")
        self.assertIn("All of ExpertOS's AI providers have reached their usage limits", str(first.exception))
        self.assertIn("earliest expected reset", str(first.exception))
        self.assertAlmostEqual(first.exception.retry_at, reset, delta=2)

        before = self.calls()
        started = time.perf_counter()
        with self.assertRaises(AIServiceError) as second:
            self.router.generate("q")
        self.assertEqual(self.calls(), before)                      # no provider was called
        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertTrue(all(a["skipped"] for a in second.exception.attempts))
        self.assertIn("usage limits", str(second.exception))

    def test_primary_quota_with_broken_backups_is_described_accurately(self):
        self.openrouter.side_effect = AllModelsExhausted(ACCOUNT_LIMIT, "daily", retry_at=time.time() + 600)
        self.gemini.side_effect = google_exceptions.ServiceUnavailable("overloaded")
        self.groq.side_effect = groq_error(404, "model does not exist")
        with self.assertRaises(AIServiceError) as ctx:
            self.router.generate("q")
        message = str(ctx.exception)
        self.assertIn("primary AI provider's usage limit has been reached", message)
        self.assertIn("backup providers couldn't complete the request", message)

    def test_streaming_falls_back_to_non_streaming_provider(self):
        def failing_stream(*a, **k):
            raise AllModelsExhausted(ACCOUNT_LIMIT, "daily")
            yield  # pragma: no cover
        self.router.providers[0]["stream"] = failing_stream
        chunks = list(self.router.stream("q", request_type="live_turn", expert_key="Security Expert"))
        self.assertEqual(chunks, ["gemini answer"])
        call = self.ai_calls()[0]
        self.assertEqual((call["provider"], call["streamed"]), ("Gemini", 0))
        self.assertIsNotNone(call["first_token_ms"])

    def test_no_secret_or_raw_error_in_user_message(self):
        self.openrouter.side_effect = AllModelsExhausted(AUTH, "Bearer sk-or-v1-SECRET rejected")
        self.gemini.side_effect = google_exceptions.Forbidden("key AIzaSECRET blocked")
        self.groq.side_effect = groq_error(401, "Invalid API Key gsk_SECRET")
        with self.assertRaises(AIServiceError) as ctx:
            self.router.generate("q")
        text = str(ctx.exception) + json.dumps(ctx.exception.attempts)
        self.assertNotIn("SECRET", text)


class RetryAtTests(unittest.TestCase):

    def test_openrouter_reset_header(self):
        reset = time.time() + 3600
        self.assertAlmostEqual(retry_at_from_exception(openrouter_daily_limit(reset)), reset, delta=1)

    def test_google_retry_info(self):
        now = time.time()
        self.assertAlmostEqual(retry_at_from_exception(gemini_daily_quota(120), now=now), now + 120, delta=0.01)

    def test_wrapped_and_absent(self):
        try:
            try:
                raise gemini_daily_quota(60)
            except Exception as e:
                raise Exception(f"Gemini Provider Error: {e}")
        except Exception as wrapped:
            self.assertIsNotNone(retry_at_from_exception(wrapped))
        self.assertIsNone(retry_at_from_exception(ValueError("x")))


class EndpointAndMetricsTests(unittest.TestCase):
    """Through the Flask app: error payload, counting rules and retries."""

    def setUp(self):
        self.db_path = _testenv.fresh_database()
        self.client = _testenv.client(app)

    def rows(self, sql):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def recommend(self):
        return self.client.post("/expert/recommend", json={
            "expert": "Database Engineer", "answers": {"description": "A booking app"},
        })

    def test_all_providers_failing_returns_safe_structured_error(self):
        err = AIServiceError("All of ExpertOS's AI providers have reached their usage limits.", ACCOUNT_LIMIT,
                             attempts=[{"provider": "OpenRouter", "category": ACCOUNT_LIMIT, "skipped": False}],
                             retry_at=time.time() + 3600)
        with mock.patch.object(app_module, "generate_recommendation", side_effect=err):
            res = self.recommend()
        body = res.get_json()
        self.assertEqual(res.status_code, 503)
        self.assertEqual(body["code"], ACCOUNT_LIMIT)
        self.assertTrue(body["retryable"])
        self.assertTrue(body["retry_at"].endswith("+00:00"))
        self.assertEqual(body["providers"][0]["provider"], "OpenRouter")

    def test_failures_then_retry_success_count_one_consultation(self):
        ok = {"title": "T", "recommendation": "R", "description": "D", "metrics": []}
        side_effects = [AIServiceError("busy", RATE_LIMIT), AIServiceError("busy", RATE_LIMIT), ok]
        with mock.patch.object(app_module, "generate_recommendation", side_effect=side_effects):
            codes = [self.recommend().status_code for _ in range(3)]
        self.assertEqual(codes, [503, 503, 200])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM consultations")[0][0], 1)
        self.assertEqual(self.rows("SELECT success, error_category FROM operations ORDER BY id"),
                         [(0, RATE_LIMIT), (0, RATE_LIMIT), (1, None)])
        stats = self.client.get("/stats").get_json()
        self.assertEqual(stats["completed_consultations"], 1)
        self.assertEqual(stats["response_time"]["samples"], 1)   # only the success is timed

    def test_provider_rate_limit_is_not_recorded_as_server_error(self):
        router = provider_router.ProviderRouter()
        router.providers = [{"name": "P", "enabled": True,
                             "generate": mock.Mock(side_effect=AllModelsExhausted(RATE_LIMIT, "busy"))}]
        with mock.patch("services.expert_recommendation.generate", side_effect=router.generate):
            self.recommend()
        self.assertEqual(self.rows("SELECT error_category FROM operations"), [(RATE_LIMIT,)])
        self.assertEqual(self.rows("SELECT error_category, success FROM ai_calls"), [(RATE_LIMIT, 0)])


if __name__ == "__main__":
    unittest.main()
