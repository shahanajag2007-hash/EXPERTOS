"""
Deterministic tests for OpenRouter failure classification and model fallback.
The OpenAI SDK client is mocked; no network requests are made.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import os
import ssl
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx
import openai

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import openrouter_client as oc  # noqa: E402
from services import panel_engine  # noqa: E402
from services.errors import (  # noqa: E402
    classify_exception, ProviderError,
    TLS, CONNECTION, TIMEOUT, AUTH, CREDITS, FORBIDDEN, ACCOUNT_LIMIT,
    RATE_LIMIT, MODEL_NOT_FOUND, SERVER, EMPTY, MALFORMED, BAD_REQUEST,
)

_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
MODELS = ["model/a", "model/b", "model/c"]


def status_error(status, message="error"):
    response = httpx.Response(status, request=_REQUEST, json={"error": {"message": message}})
    return openai.APIStatusError(f"Error code: {status} - {message}", response=response, body=None)


def tls_error():
    try:
        try:
            raise ssl.SSLCertVerificationError("certificate verify failed: unable to get local issuer certificate")
        except ssl.SSLCertVerificationError as inner:
            raise openai.APIConnectionError(request=_REQUEST) from inner
    except openai.APIConnectionError as exc:
        return exc


def completion(text="Hello", finish_reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)],
        model_extra={},
    )


class ClassificationTests(unittest.TestCase):

    def test_status_codes(self):
        cases = {
            401: AUTH, 402: CREDITS, 403: FORBIDDEN, 404: MODEL_NOT_FOUND,
            400: BAD_REQUEST, 500: SERVER, 502: SERVER, 503: SERVER,
        }
        for status, expected in cases.items():
            self.assertEqual(classify_exception(status_error(status)), expected, status)

    def test_openrouter_invalid_model_id_is_model_not_found(self):
        self.assertEqual(
            classify_exception(status_error(400, "foo/bar:free is not a valid model ID")),
            MODEL_NOT_FOUND,
        )

    def test_log_detail_omits_raw_body(self):
        from services.errors import log_detail
        response = httpx.Response(400, request=_REQUEST)
        exc = openai.APIStatusError(
            "Error code: 400 - {... 'user_id': 'user_123'}", response=response,
            body={"error": {"message": "bad model", "code": 400}, "user_id": "user_123"},
        )
        self.assertEqual(log_detail(exc), "HTTP 400: bad model")

    def test_rate_limits(self):
        self.assertEqual(classify_exception(status_error(429, "Provider returned error")), RATE_LIMIT)
        self.assertEqual(
            classify_exception(status_error(429, "Rate limit exceeded: free-models-per-day")),
            ACCOUNT_LIMIT,
        )

    def test_network_failures(self):
        self.assertEqual(classify_exception(tls_error()), TLS)
        self.assertEqual(classify_exception(openai.APITimeoutError(request=_REQUEST)), TIMEOUT)
        self.assertEqual(classify_exception(openai.APIConnectionError(request=_REQUEST)), CONNECTION)

    def test_wrapped_errors_keep_their_cause(self):
        # Groq/Gemini providers re-raise as plain Exception inside `except`.
        try:
            try:
                raise status_error(401, "invalid api key")
            except Exception as e:
                raise Exception(f"Groq Provider Error: {e}")
        except Exception as wrapped:
            self.assertEqual(classify_exception(wrapped), AUTH)


class OpenRouterFallbackTests(unittest.TestCase):

    def setUp(self):
        patches = [
            mock.patch.object(oc, "MODEL_REGISTRY", [{"id": m, "name": m} for m in MODELS]),
            mock.patch.object(oc, "_health", oc._ModelHealth()),
            mock.patch.object(oc, "OPENROUTER_API_KEY", "test-key"),
            mock.patch.object(oc.time, "sleep"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.create = mock.Mock()
        client_patch = mock.patch.object(oc, "_client")
        client = client_patch.start()
        self.addCleanup(client_patch.stop)
        client.chat.completions.create = self.create

    def models_called(self):
        return [c.kwargs["model"] for c in self.create.call_args_list]

    def test_retired_model_falls_back_and_is_skipped_next_time(self):
        self.create.side_effect = [status_error(404, "No endpoints found"), completion("ok")]
        self.assertEqual(oc.generate("hi"), "ok")
        self.assertEqual(self.models_called(), ["model/a", "model/b"])

        self.create.reset_mock(side_effect=True)
        self.create.return_value = completion("ok again")
        oc.generate("hi")
        self.assertEqual(self.models_called(), ["model/b"])

    def test_model_rate_limit_moves_on_without_same_model_retry(self):
        self.create.side_effect = [status_error(429, "Provider returned error"), completion("ok")]
        self.assertEqual(oc.generate("hi"), "ok")
        self.assertEqual(self.models_called(), ["model/a", "model/b"])

    def test_server_error_is_retried_on_same_model(self):
        self.create.side_effect = [status_error(502), completion("ok")]
        self.assertEqual(oc.generate("hi"), "ok")
        self.assertEqual(self.models_called(), ["model/a", "model/a"])

    def test_retries_are_bounded(self):
        self.create.side_effect = status_error(503)
        with self.assertRaises(oc.AllModelsExhausted) as ctx:
            oc.generate("hi")
        self.assertEqual(ctx.exception.category, SERVER)
        self.assertEqual(self.create.call_count, len(MODELS) * (oc._MAX_RETRIES + 1))

    def test_empty_and_malformed_responses_fall_back(self):
        self.create.side_effect = [
            completion("", finish_reason="stop"),
            SimpleNamespace(choices=None, model_extra={}),
            completion("ok"),
        ]
        self.assertEqual(oc.generate("hi"), "ok")
        self.assertEqual(self.models_called(), MODELS)

    def test_answer_cut_off_by_reasoning_is_retried_with_bigger_budget(self):
        self.create.side_effect = [completion("", finish_reason="length"), completion("ok")]
        self.assertEqual(oc.generate("hi", max_tokens=1200), "ok")
        self.assertEqual(self.models_called(), ["model/a", "model/a"])
        budgets = [c.kwargs["max_tokens"] for c in self.create.call_args_list]
        self.assertEqual(budgets, [1200, 2400])

    def test_budget_is_raised_only_once_per_model(self):
        self.create.side_effect = [
            completion("", finish_reason="length"),
            completion("", finish_reason="length"),
            completion("ok"),
        ]
        self.assertEqual(oc.generate("hi"), "ok")
        self.assertEqual(self.models_called(), ["model/a", "model/a", "model/b"])

    def test_reasoning_is_disabled_by_default(self):
        self.create.return_value = completion("ok")
        oc.generate("hi")
        self.assertEqual(self.create.call_args.kwargs["extra_body"], {"reasoning": {"enabled": False}})

    def test_upstream_error_inside_200_response_is_classified(self):
        self.create.side_effect = [
            SimpleNamespace(choices=None, model_extra={"error": {"code": 429, "message": "busy"}}),
            completion("ok"),
        ]
        self.assertEqual(oc.generate("hi"), "ok")

    def test_provider_wide_failures_stop_immediately(self):
        for error, category in [
            (status_error(401, "No auth credentials found"), AUTH),
            (status_error(402, "Insufficient credits"), CREDITS),
            (status_error(429, "Rate limit exceeded: free-models-per-day"), ACCOUNT_LIMIT),
            (tls_error(), TLS),
        ]:
            with self.subTest(category=category):
                self.create.reset_mock(side_effect=True)
                oc._health = oc._ModelHealth()
                self.create.side_effect = error
                with self.assertRaises(oc.AllModelsExhausted) as ctx:
                    oc.generate("hi")
                self.assertEqual(ctx.exception.category, category)
                self.assertEqual(self.models_called(), ["model/a"])

    def test_connection_errors_retry_then_stop(self):
        self.create.side_effect = openai.APIConnectionError(request=_REQUEST)
        with self.assertRaises(oc.AllModelsExhausted) as ctx:
            oc.generate("hi")
        self.assertEqual(ctx.exception.category, CONNECTION)
        self.assertEqual(self.models_called(), ["model/a"] * (oc._MAX_RETRIES + 1))

    def test_timeout_moves_to_next_model(self):
        self.create.side_effect = [openai.APITimeoutError(request=_REQUEST), completion("ok")]
        self.assertEqual(oc.generate("hi"), "ok")
        self.assertEqual(self.models_called(), ["model/a", "model/b"])

    def test_models_in_cooldown_are_tried_when_nothing_else_is_left(self):
        for m in MODELS:
            oc._health.record_failure(m)
            oc._health.record_failure(m)
        self.create.return_value = completion("ok")
        self.assertEqual(oc.generate("hi"), "ok")

    def test_missing_key_is_a_configuration_error(self):
        with mock.patch.object(oc, "OPENROUTER_API_KEY", None):
            with self.assertRaises(oc.AllModelsExhausted) as ctx:
                oc.generate("hi")
        self.assertEqual(ctx.exception.category, "not_configured")
        self.create.assert_not_called()

    def test_summary_prefers_transient_failure(self):
        self.create.side_effect = [
            status_error(404), status_error(429, "Provider returned error"), status_error(403),
        ]
        with self.assertRaises(oc.AllModelsExhausted) as ctx:
            oc.generate("hi")
        self.assertEqual(ctx.exception.category, RATE_LIMIT)


class GeminiTruncationTests(unittest.TestCase):
    """Gemini's hidden thinking can exhaust the budget and cut answers off."""

    def _response(self, text, reason):
        return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=reason))])

    def test_truncated_answer_is_rejected_not_returned(self):
        from providers import gemini_provider
        with mock.patch.object(gemini_provider.model, "generate_content",
                               return_value=self._response("When a user attempts to book", "MAX_TOKENS")):
            with self.assertRaises(ProviderError) as ctx:
                gemini_provider.generate("q", max_tokens=400)
        self.assertEqual(ctx.exception.category, EMPTY)

    def test_budget_includes_thinking_headroom(self):
        from providers import gemini_provider
        with mock.patch.object(gemini_provider.model, "generate_content",
                               return_value=self._response("Full answer.", "STOP")) as gen:
            self.assertEqual(gemini_provider.generate("q", max_tokens=400), "Full answer.")
        config = gen.call_args.kwargs["generation_config"]
        self.assertEqual(config.max_output_tokens, 400 + gemini_provider.THINKING_HEADROOM)


class PanelIsolationTests(unittest.TestCase):

    def test_each_expert_gets_its_own_instructions_concurrently(self):
        experts = ["Software Architect", "Database Engineer", "Security Expert", "Cloud Consultant"]
        names = {
            "Software Architect": "Ethan Walker", "Database Engineer": "Alex Morgan",
            "Security Expert": "Sarah Patel", "Cloud Consultant": "Daniel Brooks",
        }
        barrier = threading.Barrier(len(experts), timeout=5)
        prompts = []

        def fake_generate(prompt, **kwargs):
            if "Panel Coordinator" in prompt:
                return '{"panel_verdict": "v"}'
            prompts.append(prompt)
            barrier.wait()  # only passes if all experts run at the same time
            speaker = next(n for n in names.values() if f"You are {n}." in prompt)
            return f"Answer from {speaker}"

        with mock.patch.object(panel_engine, "generate", side_effect=fake_generate):
            result = panel_engine.run_panel(experts, "Booking app with React and Flask")

        self.assertEqual(len(prompts), 4)
        for p in prompts:
            self.assertIn("Booking app with React and Flask", p)
        for r in result["responses"]:
            self.assertEqual(r["status"], "success")
            self.assertEqual(r["response"], f"Answer from {names[r['expert_key']]}")
            self.assertEqual(r["expert_name"], names[r["expert_key"]])
        self.assertEqual(result["synthesis"], {"panel_verdict": "v"})


if __name__ == "__main__":
    unittest.main()
