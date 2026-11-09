"""
Live multi-expert consultation room. AI calls are mocked.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import json
import unittest
from unittest import mock

from app import app
from services import consultations, db, live_engine
from services.errors import AIServiceError, RATE_LIMIT

EXPERTS = ["Software Architect", "Database Engineer", "Security Expert"]
NAMES = {"Software Architect": "Ethan", "Database Engineer": "Alex", "Security Expert": "Sarah"}


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


def panel_result(keys=EXPERTS, failed=()):
    return {
        "responses": [
            {"expert_key": k, "expert_role": k, "status": "error" if k in failed else "success",
             "response": f"{k} analysis"}
            for k in keys
        ],
        "synthesis": {"panel_verdict": "Sound plan"},
    }


class FakeAI:
    """Records prompts; each expert replies with a line naming itself."""

    def __init__(self, replies=None):
        self.prompts = []
        self.replies = replies or {}

    def _speaker(self, prompt):
        return next(k for k, n in NAMES.items() if prompt.startswith(f"You are {n}"))

    def stream(self, prompt, **kwargs):
        self.prompts.append(prompt)
        key = self._speaker(prompt)
        reply = self.replies.get(key, f"{NAMES[key]} point")
        if isinstance(reply, Exception):
            raise reply
        for word in reply.split(" "):
            yield word + " "


class LiveBase(unittest.TestCase):

    def setUp(self):
        _testenv.fresh_database()
        self.client = _testenv.client(app)
        self.consultation = consultations.create_consultation(
            "panel", EXPERTS, problem="A yoga booking SaaS", result=panel_result(),
        )
        self.headers = {"X-Consultation-Token": self.consultation["token"]}
        self.ai = FakeAI()
        patcher = mock.patch.object(live_engine, "stream", side_effect=self.ai.stream)
        patcher.start()
        self.addCleanup(patcher.stop)

    def open(self):
        res = self.client.post("/live/sessions", json={"consultation_id": self.consultation["id"]},
                               headers=self.headers)
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()

    def round(self, session_id, body=None):
        res = self.client.post(f"/live/sessions/{session_id}/rounds", json=body or {}, headers=self.headers)
        if res.mimetype != "text/event-stream":
            return res.status_code, res.get_json()
        return res.status_code, parse_sse(res.get_data(as_text=True))


class SessionTests(LiveBase):

    def test_open_session_lists_participants_and_agenda(self):
        session = self.open()
        self.assertEqual([p["key"] for p in session["participants"]], EXPERTS)
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["messages"], [])
        self.assertEqual(session["current_stage_label"], live_engine.AGENDA[0]["label"])

    def test_reopening_returns_the_same_session(self):
        self.assertEqual(self.open()["id"], self.open()["id"])

    def test_requires_valid_token(self):
        res = self.client.post("/live/sessions", json={"consultation_id": self.consultation["id"]},
                               headers={"X-Consultation-Token": "wrong"})
        self.assertEqual(res.status_code, 403)
        session = self.open()
        res = self.client.get(f"/live/sessions/{session['id']}", headers={"X-Consultation-Token": "wrong"})
        self.assertEqual(res.status_code, 403)

    def test_requires_panel_with_two_successful_experts(self):
        single = consultations.create_consultation("expert_room", ["Database Engineer"])
        res = self.client.post("/live/sessions", json={"consultation_id": single["id"]},
                               headers={"X-Consultation-Token": single["token"]})
        self.assertEqual(res.status_code, 409)

        thin = consultations.create_consultation(
            "panel", EXPERTS, problem="x", result=panel_result(failed=EXPERTS[1:]),
        )
        res = self.client.post("/live/sessions", json={"consultation_id": thin["id"]},
                               headers={"X-Consultation-Token": thin["token"]})
        self.assertEqual(res.status_code, 409)


class RoundTests(LiveBase):

    def complete_agenda(self, session_id):
        for _ in range(len(live_engine.AGENDA) * 3):
            state = self.client.get(f"/live/sessions/{session_id}", headers=self.headers).get_json()
            if state["agenda_complete"]:
                return state
            self.round(session_id)
        self.fail("The agenda never completed.")

    def test_agenda_round_streams_and_stores_messages_in_order(self):
        session = self.open()
        self.assertEqual(session["phase"], "expert_discussion")
        self.assertFalse(session["can_message"])
        status, events = self.round(session["id"])
        self.assertEqual(status, 200)

        kinds = [e for e, _ in events]
        self.assertEqual(kinds[0], "turn_start")
        self.assertIn("token", kinds)
        self.assertEqual(kinds[-1], "round_done")

        state = events[-1][1]
        experts = [m["expert_key"] for m in state["messages"]]
        self.assertEqual(experts, EXPERTS[:live_engine.TURNS_PER_ROUND])
        self.assertEqual([m["seq"] for m in state["messages"]], [1, 2])
        self.assertEqual([m["agenda_stage"] for m in state["messages"]], [0, 0])
        # Two of the three required experts have spoken: the item isn't done yet.
        self.assertEqual((state["stage"], state["stage_speakers_done"], state["stage_speakers_needed"]), (0, 2, 3))
        self.assertFalse(state["busy"])

        # The second speaker sees what the first said.
        self.assertIn("Ethan (Senior Software Architect): Ethan point", self.ai.prompts[1])
        self.assertIn("Agenda item 1 of 5: " + live_engine.AGENDA[0]["label"], self.ai.prompts[0])

    def test_agenda_item_completes_only_when_every_required_expert_spoke(self):
        session = self.open()
        self.round(session["id"])
        _, events = self.round(session["id"])
        state = events[-1][1]
        # Only the expert who hadn't contributed yet speaks, then the item is done.
        self.assertEqual([m["expert_key"] for m in state["messages"]][2:], ["Security Expert"])
        self.assertEqual(state["stage"], 1)

    def test_whole_agenda_completes_in_order_then_unlocks_the_client(self):
        session = self.open()
        state = self.complete_agenda(session["id"])
        stages = [m["agenda_stage"] for m in state["messages"]]
        self.assertEqual(stages, sorted(stages))
        for stage in range(len(live_engine.AGENDA)):
            self.assertEqual({m["expert_key"] for m in state["messages"] if m["agenda_stage"] == stage},
                             set(EXPERTS))
        self.assertEqual(state["phase"], "user_interaction")
        self.assertTrue(state["can_message"])
        self.assertEqual(state["rounds"], 0)    # agenda rounds don't use the question allowance

    def test_failed_turns_do_not_complete_an_agenda_item(self):
        self.ai.replies = {k: AIServiceError("busy", RATE_LIMIT) for k in EXPERTS}
        session = self.open()
        for _ in range(3):
            _, events = self.round(session["id"])
        self.assertEqual(events[-1][1]["stage"], 0)
        self.assertEqual(events[-1][1]["messages"], [])

    def test_client_cannot_interrupt_the_agenda(self):
        session = self.open()
        status, body = self.round(session["id"], {"message": "Can I ask something?", "message_id": "m1"})
        self.assertEqual(status, 409)
        self.assertIn("still working through the agenda", body["error"])
        state = self.client.get(f"/live/sessions/{session['id']}", headers=self.headers).get_json()
        self.assertEqual(state["messages"], [])

    def test_client_question_goes_to_relevant_expert_first(self):
        session = self.open()
        self.complete_agenda(session["id"])
        self.ai.prompts.clear()
        _, events = self.round(session["id"], {
            "message": "Will the postgres schema handle double bookings?", "message_id": "m1",
        })
        new = [m for m in events[-1][1]["messages"] if m["agenda_stage"] is None]
        self.assertEqual(new[0]["role"], "client")
        self.assertEqual(new[1]["expert_key"], "Database Engineer")
        self.assertIn("postgres schema", self.ai.prompts[0])
        self.assertIn("Don't restart the agenda", self.ai.prompts[0])
        self.assertEqual(events[-1][1]["rounds"], 1)

    def test_client_can_address_expert_by_name(self):
        session = self.open()
        self.complete_agenda(session["id"])
        _, events = self.round(session["id"], {"message": "Sarah, what do you think?", "message_id": "m1"})
        new = [m for m in events[-1][1]["messages"] if m["agenda_stage"] is None]
        self.assertEqual(new[1]["expert_key"], "Security Expert")

    def test_question_for_several_named_experts_gets_each_of_them(self):
        session = self.open()
        self.complete_agenda(session["id"])
        _, events = self.round(session["id"], {"message": "Ethan and Sarah, do you agree on auth?",
                                               "message_id": "m1"})
        new = [m["expert_key"] for m in events[-1][1]["messages"] if m["role"] == "expert" and m["agenda_stage"] is None]
        self.assertEqual(new, ["Software Architect", "Security Expert"])

    def test_greeting_gets_one_brief_social_reply(self):
        session = self.open()
        self.complete_agenda(session["id"])
        self.ai.prompts.clear()
        _, events = self.round(session["id"], {"message": "Hi!", "message_id": "m1"})
        new = [m for m in events[-1][1]["messages"] if m["role"] == "expert" and m["agenda_stage"] is None]
        self.assertEqual(len(new), 1)
        self.assertEqual(len(self.ai.prompts), 1)
        self.assertIn("The user is greeting you", self.ai.prompts[0])
        self.assertIn("Do NOT analyse the project", self.ai.prompts[0])

    def test_optional_expert_may_pass(self):
        session = self.open()
        self.complete_agenda(session["id"])
        # No expert is named and no topic matches: one expert answers, a second may PASS.
        self.ai.replies = {k: "PASS" for k in EXPERTS}
        _, events = self.round(session["id"], {"message": "What would you change first?", "message_id": "m1"})
        kinds = [e for e, _ in events]
        self.assertEqual(kinds.count("turn_skipped"), 1)
        new = [m for m in events[-1][1]["messages"] if m["agenda_stage"] is None]
        self.assertEqual([m["role"] for m in new], ["client", "expert"])

    def test_duplicate_client_message_is_rejected(self):
        session = self.open()
        self.complete_agenda(session["id"])
        self.round(session["id"], {"message": "Hello", "message_id": "same"})
        status, body = self.round(session["id"], {"message": "Hello", "message_id": "same"})
        self.assertEqual(status, 409)
        state = self.client.get(f"/live/sessions/{session['id']}", headers=self.headers).get_json()
        self.assertEqual(sum(m["role"] == "client" for m in state["messages"]), 1)

    def test_resending_an_unanswered_message_retries_without_duplicating_it(self):
        session = self.open()
        self.complete_agenda(session["id"])
        self.ai.replies = {k: AIServiceError("busy", RATE_LIMIT) for k in EXPERTS}
        _, events = self.round(session["id"], {"message": "Is Postgres enough?", "message_id": "q1"})
        new = [m["role"] for m in events[-1][1]["messages"] if m["agenda_stage"] is None]
        self.assertEqual(new, ["client"])

        self.ai.replies = {}
        status, events = self.round(session["id"], {"message": "Is Postgres enough?", "message_id": "q1"})
        self.assertEqual(status, 200)
        roles = [m["role"] for m in events[-1][1]["messages"] if m["agenda_stage"] is None]
        self.assertEqual(roles.count("client"), 1)
        self.assertIn("expert", roles)

    def test_concurrent_round_is_rejected_while_busy(self):
        session = self.open()
        live_engine._acquire(session["id"])
        status, body = self.round(session["id"])
        self.assertEqual(status, 409)
        self.assertIn("still responding", body["error"])
        live_engine._release(session["id"])
        self.assertEqual(self.round(session["id"])[0], 200)

    def test_stale_lock_expires(self):
        session = self.open()
        with db.connection(write=True) as conn:
            conn.execute("UPDATE live_sessions SET busy_since = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                         (session["id"],))
        self.assertEqual(self.round(session["id"])[0], 200)

    def test_one_expert_failing_does_not_stop_the_round(self):
        self.ai.replies = {"Software Architect": AIServiceError("busy", RATE_LIMIT)}
        session = self.open()
        _, events = self.round(session["id"])
        errors = [p for e, p in events if e == "turn_error"]
        self.assertEqual(errors[0]["expert_key"], "Software Architect")
        self.assertEqual([m["expert_key"] for m in events[-1][1]["messages"]], ["Database Engineer"])
        self.assertFalse(events[-1][1]["busy"])

    def test_input_validation(self):
        session = self.open()
        self.assertEqual(self.round(session["id"], {"message": "   ", "message_id": "a"})[0], 400)
        self.assertEqual(self.round(session["id"], {"message": "x" * 2001, "message_id": "b"})[0], 400)
        self.assertEqual(self.round(session["id"], {"message": "hi"})[0], 400)  # no message ID

    def test_agenda_and_round_limits(self):
        session = self.open()
        self.complete_agenda(session["id"])
        status, body = self.round(session["id"])
        self.assertEqual(status, 409)
        self.assertIn("agenda", body["error"])
        # The client can ask questions until the question limit.
        with mock.patch.object(live_engine, "MAX_ROUNDS", 1):
            self.assertEqual(self.round(session["id"], {"message": "One more", "message_id": "x"})[0], 200)
            self.assertEqual(self.round(session["id"], {"message": "Again", "message_id": "y"})[0], 409)

    def test_client_disconnect_releases_lock(self):
        session = self.open()
        events = live_engine.run_round(session["id"], self.consultation["token"])
        next(events)          # stream started
        events.close()        # client went away mid-round
        self.assertEqual(self.round(session["id"])[0], 200)


class CloseAndSummaryTests(LiveBase):

    SUMMARY = {
        "project_understanding": "A booking SaaS.", "main_problems": ["Double booking"],
        "expert_insights": [{"expert": "Alex", "insight": "Use row locks"}, {"expert": "", "insight": ""}],
        "agreements": ["Use Postgres"], "disagreements": [], "decisions": ["Postgres"],
        "risks": ["Double booking"], "recommended_solution": "Modular monolith.",
        "next_steps": ["Model schema"], "unanswered_questions": [], "conclusion": "Proceed.",
    }

    def test_close_generates_summary_from_transcript(self):
        session = self.open()
        self.round(session["id"])
        with mock.patch.object(live_engine, "generate", return_value=json.dumps(self.SUMMARY)) as gen:
            res = self.client.post(f"/live/sessions/{session['id']}/close", headers=self.headers)
        state = res.get_json()
        self.assertEqual(state["status"], "closed")
        self.assertEqual(state["phase"], "closed")
        self.assertEqual(state["summary"]["conclusion"], "Proceed.")
        self.assertEqual(state["summary"]["expert_insights"], [{"expert": "Alex", "insight": "Use row locks"}])
        self.assertEqual((state["summary"]["agenda_completed"], state["summary"]["agenda_total"]), (0, 5))
        self.assertEqual(len(state["messages"]), 2)          # transcript preserved
        prompt = gen.call_args.args[0]
        self.assertIn("Ethan (Senior Software Architect): Ethan point", prompt)
        # Ended early: the summary must not present the agenda as finished.
        self.assertIn("1. Reviewing the project: NOT reached", prompt)
        self.assertIn("ended before the agenda was complete", prompt)

        # Reopening returns the closed session with its summary; no more discussion.
        reopened = self.open()
        self.assertEqual((reopened["status"], reopened["summary"]["conclusion"]), ("closed", "Proceed."))

        # No more discussion after closing.
        self.assertEqual(self.round(session["id"])[0], 409)

    def test_summary_failure_keeps_transcript_and_can_be_retried(self):
        session = self.open()
        self.round(session["id"])
        with mock.patch.object(live_engine, "generate", return_value="not json"):
            state = self.client.post(f"/live/sessions/{session['id']}/close", headers=self.headers).get_json()
        self.assertIsNone(state["summary"])
        self.assertTrue(state["summary_error"])
        self.assertEqual(len(state["messages"]), 2)

        with mock.patch.object(live_engine, "generate", return_value=json.dumps(self.SUMMARY)):
            state = self.client.post(f"/live/sessions/{session['id']}/summary", headers=self.headers).get_json()
        self.assertEqual(state["summary"]["recommended_solution"], "Modular monolith.")

    def test_closing_without_discussion_reports_nothing_to_summarise(self):
        session = self.open()
        with mock.patch.object(live_engine, "generate") as gen:
            state = self.client.post(f"/live/sessions/{session['id']}/close", headers=self.headers).get_json()
        gen.assert_not_called()
        self.assertIn("no discussion", state["summary_error"])

    def test_closing_mid_round_stops_further_speakers(self):
        session = self.open()
        events = live_engine.run_round(session["id"], self.consultation["token"])
        for event, _ in events:
            if event == "message":
                # The client ends the session after the first expert spoke.
                with db.connection(write=True) as conn:
                    conn.execute("UPDATE live_sessions SET status = 'closed' WHERE id = ?", (session["id"],))
        state = live_engine.get_session(session["id"], self.consultation["token"])
        self.assertEqual(len(state["messages"]), 1)

    def test_deleting_consultation_removes_transcript(self):
        session = self.open()
        self.round(session["id"])
        self.client.delete(f"/consultations/{self.consultation['id']}", headers=self.headers)
        state = self.client.get(f"/live/sessions/{session['id']}", headers=self.headers).get_json()
        self.assertEqual(state["messages"], [])
        self.assertEqual(state["status"], "closed")
        self.assertIsNone(state["problem"])

    def test_close_waits_for_a_turn_being_written(self):
        session = self.open()
        live_engine._acquire(session["id"])          # a round is running
        import threading

        def finish_turn():
            live_engine._append_message(session["id"], "expert", "Last point", expert_key="Database Engineer",
                                        agenda_stage=0)
            live_engine._release(session["id"])

        threading.Timer(0.6, finish_turn).start()
        with mock.patch.object(live_engine, "generate", return_value=json.dumps(self.SUMMARY)) as gen:
            state = self.client.post(f"/live/sessions/{session['id']}/close", headers=self.headers).get_json()
        self.assertIn("Last point", gen.call_args.args[0])
        self.assertEqual(state["messages"][-1]["content"], "Last point")

    def test_summary_parser_normalises_types(self):
        summary = live_engine.parse_summary(
            '```json\n{"conclusion": "Done", "main_problems": "One", "risks": null, "next_steps": ["a", ""]}\n```'
        )
        self.assertEqual(summary["main_problems"], ["One"])
        self.assertEqual(summary["risks"], [])
        self.assertEqual(summary["next_steps"], ["a"])


if __name__ == "__main__":
    unittest.main()
