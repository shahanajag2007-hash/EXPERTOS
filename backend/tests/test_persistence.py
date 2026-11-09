"""
Persistence, statistics, ratings, metrics, contact and streaming endpoints.
AI calls are mocked; every test gets an empty temporary database.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import app as app_module
from app import app
from services import consultations, db, metrics
from services.errors import AIServiceError, TIMEOUT, RATE_LIMIT

RECOMMENDATION = {
    "title": "T", "recommendation": "Add an index", "description": "D",
    "metrics": [{"name": "p95 latency", "value": "Under 200 ms"}],
}


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


class Base(unittest.TestCase):

    def setUp(self):
        self.db_path = _testenv.fresh_database()
        self.client = _testenv.client(app)
        app_module.rating_limiter.hits.clear()
        app_module.contact_limiter.hits.clear()

    def rows(self, sql, *params):
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def recommend(self, expert="Database Engineer"):
        with mock.patch.object(app_module, "generate_recommendation", return_value=dict(RECOMMENDATION)):
            res = self.client.post("/expert/recommend", json={
                "expert": expert, "answers": {"description": "A booking app"},
            })
        self.assertEqual(res.status_code, 200)
        return res.get_json()["consultation"]


class MigrationTests(Base):

    def test_schema_created_once(self):
        tables = {r[0] for r in self.rows("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"consultations", "ratings", "operations", "ai_calls", "live_sessions",
                         "live_messages", "contact_messages"} <= tables)
        db.reset_for_tests()
        db.init_db()
        # Each migration is applied exactly once, even after a second init.
        expected = len(list(db.MIGRATIONS_DIR.glob("*.sql")))
        self.assertGreaterEqual(expected, 2)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM schema_migrations")[0][0], expected)
        columns = {r[1] for r in self.rows("PRAGMA table_info(ai_calls)")}
        self.assertIn("provider_attempts", columns)


class StatsTests(Base):

    def test_empty_installation_shows_real_initial_values(self):
        stats = self.client.get("/stats").get_json()
        self.assertEqual(stats["completed_consultations"], 0)
        self.assertEqual(stats["active_experts"], 6)
        self.assertEqual(stats["ratings"]["total"], 0)
        self.assertIsNone(stats["ratings"]["satisfaction_rate"])
        self.assertEqual(stats["response_time"]["status"], "measuring")
        self.assertIsNone(stats["response_time"]["average_seconds"])

    def test_completed_consultation_is_counted(self):
        self.recommend()
        stats = self.client.get("/stats").get_json()
        self.assertEqual(stats["completed_consultations"], 1)
        self.assertEqual(stats["experts"]["Database Engineer"]["consultations"], 1)
        self.assertEqual(stats["response_time"]["status"], "measured")
        self.assertEqual(stats["response_time"]["samples"], 1)

    def test_failed_request_is_not_a_consultation_but_is_measured(self):
        with mock.patch.object(app_module, "generate_recommendation",
                               side_effect=AIServiceError("busy", RATE_LIMIT)):
            res = self.client.post("/expert/recommend", json={
                "expert": "Database Engineer", "answers": {"description": "x"},
            })
        self.assertEqual(res.status_code, 503)
        self.assertEqual(self.client.get("/stats").get_json()["completed_consultations"], 0)
        self.assertEqual(self.rows("SELECT success, error_category FROM operations"), [(0, "rate_limit")])

    def test_empty_answers_rejected_before_calling_ai(self):
        with mock.patch.object(app_module, "generate_recommendation") as gen:
            res = self.client.post("/expert/recommend", json={"expert": "Database Engineer", "answers": {}})
        self.assertEqual(res.status_code, 400)
        gen.assert_not_called()

    def test_panel_counts_once_and_credits_each_participating_expert(self):
        def fake(prompt, **kw):
            if "Panel Coordinator" in prompt:
                return '{"panel_verdict": "v"}'
            if "Sarah Patel" in prompt:
                raise AIServiceError("down")
            return "## Assessment\nok"

        with mock.patch("services.panel_engine.generate", side_effect=fake):
            body = self.client.post("/panel", json={
                "problem": "Booking app",
                "experts": ["Software Architect", "Database Engineer", "Security Expert"],
            }).get_json()

        self.assertIsNotNone(body["consultation"]["token"])
        stats = self.client.get("/stats").get_json()
        self.assertEqual(stats["completed_consultations"], 1)
        self.assertEqual(stats["experts"]["Software Architect"]["consultations"], 1)
        self.assertEqual(stats["experts"]["Security Expert"]["consultations"], 0)  # failed expert

    def test_panel_with_no_successful_expert_is_not_counted(self):
        with mock.patch("services.panel_engine.generate", side_effect=AIServiceError("down")):
            body = self.client.post("/panel", json={"problem": "x", "experts": ["Cloud Consultant"]}).get_json()
        self.assertIsNone(body["consultation"])
        self.assertEqual(self.client.get("/stats").get_json()["completed_consultations"], 0)


class RatingTests(Base):

    def rate(self, consultation, stars, feedback="", token=None):
        return self.client.post(
            f"/consultations/{consultation['id']}/rating",
            json={"stars": stars, "feedback": feedback},
            headers={"X-Consultation-Token": token if token is not None else consultation["token"]},
        )

    def test_valid_rating_is_saved_and_duplicates_rejected(self):
        c = self.recommend()
        self.assertEqual(self.rate(c, 5, "Great").status_code, 201)
        self.assertEqual(self.rate(c, 1).status_code, 409)
        self.assertEqual(self.rows("SELECT stars, feedback FROM ratings"), [(5, "Great")])

        status = self.client.get(f"/consultations/{c['id']}/rating",
                                 headers={"X-Consultation-Token": c["token"]}).get_json()
        self.assertEqual(status, {"rated": True, "stars": 5})

    def test_invalid_ratings(self):
        c = self.recommend()
        for stars in (0, 6, "5", 4.5, True, None):
            with self.subTest(stars=stars):
                self.assertEqual(self.rate(c, stars).status_code, 400)
        self.assertEqual(self.rate(c, 4, "x" * 1001).status_code, 400)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM ratings")[0][0], 0)

    def test_token_is_required(self):
        c = self.recommend()
        self.assertEqual(self.rate(c, 5, token="").status_code, 403)
        self.assertEqual(self.rate(c, 5, token="wrong").status_code, 403)
        self.assertEqual(self.rate({"id": "unknown", "token": c["token"]}, 5).status_code, 403)

    def test_satisfaction_rate_from_positive_ratings(self):
        for stars in (5, 4, 2):
            self.rate(self.recommend(), stars)
        ratings = self.client.get("/stats").get_json()["ratings"]
        self.assertEqual(ratings["total"], 3)
        self.assertEqual(ratings["positive"], 2)
        self.assertEqual(ratings["satisfaction_rate"], 66.7)
        self.assertEqual(ratings["average_stars"], 3.67)

        expert = self.client.get("/stats").get_json()["experts"]["Database Engineer"]
        self.assertEqual(expert["ratings"], 3)
        self.assertEqual(expert["average_stars"], 3.7)

    def test_rating_rate_limit(self):
        app_module.rating_limiter.limit = 2
        try:
            codes = [self.rate(self.recommend(), 5).status_code for _ in range(3)]
        finally:
            app_module.rating_limiter.limit = 10
        self.assertEqual(codes, [201, 201, 429])


class MetricsTests(Base):

    def test_summary_statistics(self):
        rows = [(ms, 1, 0) for ms in (1000, 2000, 3000, 4000, 40000)] + [(5000, 0, 1), (100, 0, 0)]
        s = metrics.summarize(rows)
        self.assertEqual(s["requests"], 7)
        self.assertEqual(s["successful"], 5)
        self.assertEqual(s["success_rate"], 71.4)
        self.assertEqual(s["timeout_rate"], 14.3)
        self.assertEqual(s["average_seconds"], 10.0)
        self.assertEqual(s["median_seconds"], 3.0)
        self.assertEqual(s["p95_seconds"], 40.0)
        self.assertEqual(s["within_target_rate"], 80.0)

    def test_empty_summary(self):
        s = metrics.summarize([])
        self.assertIsNone(s["average_seconds"])
        self.assertIsNone(s["success_rate"])

    def test_track_operation_records_success_and_timeout(self):
        with metrics.track_operation(metrics.EXPERT_CHAT, "Security Expert"):
            pass
        with self.assertRaises(AIServiceError):
            with metrics.track_operation(metrics.EXPERT_CHAT):
                raise AIServiceError("slow", TIMEOUT)
        rows = self.rows("SELECT request_type, expert_key, success, error_category, timed_out FROM operations")
        self.assertEqual(rows, [("expert_chat", "Security Expert", 1, None, 0),
                                ("expert_chat", None, 0, "timeout", 1)])

    def test_homepage_average_uses_single_expert_requests_only(self):
        for request_type, ms in (("recommendation", 10000), ("expert_chat", 20000), ("panel", 90000)):
            t = metrics.Timer()
            t._start -= ms / 1000
            metrics.record_operation(request_type, t, True)
        avg = self.client.get("/stats").get_json()["response_time"]["average_seconds"]
        self.assertAlmostEqual(avg, 15.0, delta=0.2)

        report = self.client.get("/stats/performance").get_json()
        self.assertEqual(report["by_request_type"]["panel"]["requests"], 1)
        self.assertEqual(report["single_expert_requests"]["requests"], 2)
        self.assertEqual(report["overall"]["requests"], 3)

    def test_provider_router_records_ai_calls(self):
        from providers import provider_router
        router = provider_router.ProviderRouter()
        router.providers = [{"name": "P", "generate": lambda *a, **k: "hi", "model": "m1", "enabled": True}]
        router.generate("x", request_type="panel_expert", expert_key="Cloud Consultant")
        self.assertEqual(
            self.rows("SELECT request_type, expert_key, provider, model, success FROM ai_calls"),
            [("panel_expert", "Cloud Consultant", "P", "m1", 1)],
        )

    def test_metrics_failure_never_breaks_requests(self):
        with mock.patch.object(db, "connection", side_effect=db.DatabaseError("down")):
            metrics.record_operation("expert_chat", metrics.Timer(), True)  # must not raise


class DeletionAndRetentionTests(Base):

    def panel_consultation(self):
        return consultations.create_consultation(
            "panel", ["Software Architect"], problem="Secret project", result={"responses": []},
        )

    def test_user_can_delete_content_without_changing_counts(self):
        c = self.panel_consultation()
        res = self.client.delete(f"/consultations/{c['id']}", headers={"X-Consultation-Token": c["token"]})
        self.assertEqual(res.status_code, 200)
        problem, deleted = self.rows("SELECT problem, content_deleted_at FROM consultations")[0]
        self.assertIsNone(problem)
        self.assertIsNotNone(deleted)
        self.assertEqual(self.client.get("/stats").get_json()["completed_consultations"], 1)

    def test_delete_requires_token(self):
        c = self.panel_consultation()
        res = self.client.delete(f"/consultations/{c['id']}", headers={"X-Consultation-Token": "nope"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.rows("SELECT problem FROM consultations")[0][0], "Secret project")

    def test_retention_purges_old_content(self):
        c = self.panel_consultation()
        old = (datetime.now(timezone.utc) - timedelta(days=consultations.CONTENT_RETENTION_DAYS + 1)).isoformat()
        with db.connection(write=True) as conn:
            conn.execute("UPDATE consultations SET created_at = ? WHERE id = ?", (old, c["id"]))
        consultations.purge_expired_content()
        self.assertIsNone(self.rows("SELECT problem FROM consultations")[0][0])

    def test_token_is_stored_hashed(self):
        c = self.panel_consultation()
        stored = self.rows("SELECT token_hash FROM consultations")[0][0]
        self.assertNotEqual(stored, c["token"])
        self.assertNotIn(c["token"], open(self.db_path, "rb").read().decode("latin-1"))


class DatabaseErrorTests(Base):

    def test_unavailable_database_returns_503(self):
        os.environ["EXPERTOS_DB_PATH"] = os.path.dirname(self.db_path)  # a directory: can't be opened
        db.reset_for_tests()
        res = self.client.get("/stats")
        self.assertEqual(res.status_code, 503)
        self.assertIn("storage", res.get_json()["error"])


class ContactTests(Base):

    VALID = {"name": "Ana", "email": "ana@example.com", "subject": "Hello", "message": "I have a question."}

    def test_valid_message_is_saved(self):
        self.assertEqual(self.client.post("/contact", json=self.VALID).status_code, 201)
        self.assertEqual(self.rows("SELECT email, subject FROM contact_messages"), [("ana@example.com", "Hello")])

    def test_validation(self):
        for field, value in (("email", "not-an-email"), ("subject", ""), ("message", "short")):
            with self.subTest(field=field):
                res = self.client.post("/contact", json={**self.VALID, field: value})
                self.assertEqual(res.status_code, 400)
                self.assertIn(field, res.get_json()["fields"])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM contact_messages")[0][0], 0)

    def test_honeypot_is_silently_dropped(self):
        res = self.client.post("/contact", json={**self.VALID, "website": "spam.example"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM contact_messages")[0][0], 0)

    def test_rate_limit(self):
        codes = [self.client.post("/contact", json=self.VALID).status_code for _ in range(4)]
        self.assertEqual(codes, [201, 201, 201, 429])


class StreamingTests(Base):

    def test_expert_chat_stream(self):
        def fake_stream(prompt, timer=None, **kw):
            timer.mark_first_token()
            yield "Hello "
            yield "there"

        with mock.patch("services.ai_provider.stream", side_effect=fake_stream):
            res = self.client.post("/expert/chat/stream", json={
                "expert": "Security Expert", "message": "Is JWT ok?", "history": [],
            })
            events = parse_sse(res.get_data(as_text=True))

        self.assertEqual([e for e, _ in events], ["token", "token", "done"])
        self.assertEqual(events[-1][1]["reply"], "Hello there")
        (first_token, success), = self.rows("SELECT first_token_ms, success FROM operations")
        self.assertIsNotNone(first_token)
        self.assertEqual(success, 1)

    def test_expert_chat_stream_error_event(self):
        def failing(prompt, **kw):
            raise AIServiceError("The AI models are busy right now.", RATE_LIMIT)
            yield  # pragma: no cover

        with mock.patch("services.ai_provider.stream", side_effect=failing):
            res = self.client.post("/expert/chat/stream", json={"expert": "Security Expert", "message": "Hi"})
            events = parse_sse(res.get_data(as_text=True))

        self.assertEqual(events[-1][0], "error")
        self.assertTrue(events[-1][1]["retryable"])
        self.assertEqual(self.rows("SELECT success, error_category FROM operations"), [(0, "rate_limit")])

    def test_stream_validation_happens_before_streaming(self):
        res = self.client.post("/expert/chat/stream", json={"expert": "Security Expert", "message": ""})
        self.assertEqual(res.status_code, 400)

    def test_panel_stream_emits_experts_then_synthesis_then_done(self):
        def fake(prompt, **kw):
            if "Panel Coordinator" in prompt:
                return '{"panel_verdict": "v"}'
            return "## Assessment\nok"

        with mock.patch("services.panel_engine.generate", side_effect=fake):
            res = self.client.post("/panel/stream", json={
                "problem": "Booking app", "experts": ["Software Architect", "Cloud Consultant"],
            })
            events = parse_sse(res.get_data(as_text=True))

        self.assertEqual([e for e, _ in events], ["expert", "expert", "synthesis", "done"])
        done = events[-1][1]
        self.assertEqual(done["successful_count"], 2)
        self.assertEqual(done["synthesis"], {"panel_verdict": "v"})
        self.assertIsNotNone(done["consultation"]["id"])


if __name__ == "__main__":
    unittest.main()
