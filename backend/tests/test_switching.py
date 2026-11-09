"""
Switching experts within a Start Consultation chat: the right expert is
brought in, answers with their own instructions and the shared history, and
the switch is saved so it survives a reload. AI calls are mocked.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import json
import unittest
from unittest import mock

from app import app
from providers.provider_router import ProviderRouter
from services.expert_manager import expert_manager

ANALYSIS = {k: f"{k} text" for k in
            ("architecture", "tech_stack", "database", "security", "deployment", "recommendation")}


class MatchingTests(unittest.TestCase):

    CASES = [
        ("Can Sarah join?", "Software Architect", "Security Expert"),
        ("Thanks Alex, now Sarah what about auth?", "Database Engineer", "Security Expert"),
        ("Can Sarah review the database security?", "Database Engineer", "Security Expert"),
        ("Ethan, what did Sarah say about JWT?", "Security Expert", "Software Architect"),
        ("Sarah, what did Ethan say?", "Software Architect", "Security Expert"),
        ("Let's go back to Ethan", "Design Advisor", "Software Architect"),
        ("Hi Maya, can Sarah join?", "Software Architect", "Security Expert"),
        ("Switch to the security expert", "Software Architect", "Security Expert"),
        ("Can the architect take a look?", "Security Expert", "Software Architect"),
        ("Alex said X but I want Daniel on this", "Database Engineer", "Cloud Consultant"),
        ("What database should we use?", "Software Architect", "Database Engineer"),
        ("How do we secure the database?", "Database Engineer", "Database Engineer"),
        ("How should we scale?", "Software Architect", None),
        # Mentioned in passing: not a request to switch.
        ("Earlier, Ethan said what the riskiest part was. Do you agree with him?", "Security Expert", None),
        ("Do you agree with Ethan and Alex about the database?", "Security Expert", None),
        ("Sarah, join us please", "Software Architect", "Security Expert"),
        ("Alex, can you take a look at the schema?", "Software Architect", "Database Engineer"),
        ("Ethan and Sarah both said X. Alex, weigh in", "Software Architect", "Database Engineer"),
        ("Can Sarah Patel join?", "Software Architect", "Security Expert"),
    ]

    def test_names_and_addressing_decide_the_expert(self):
        for message, current, expected in self.CASES:
            with self.subTest(message):
                self.assertEqual(expert_manager.find_manual_request(message, current=current), expected)


class ConsultationSwitchTests(unittest.TestCase):

    def setUp(self):
        _testenv.fresh_database()
        self.client = _testenv.client(app)
        with mock.patch("services.ai_provider.generate", return_value=json.dumps(ANALYSIS)):
            self.cid = self.client.post("/analyze", json={"prompt": "A clinic booking app"}).get_json()["conversation_id"]
        self.prompts = []

    def fake_generate(self, prompt, **kwargs):
        if "Consultation Router" in prompt:
            return '{"switch": false}'
        self.prompts.append(prompt)
        name = prompt.split("You are ", 1)[1].split(",", 1)[0]
        return f"Answer from {name}"

    def chat(self, message):
        with mock.patch("services.ai_provider.generate", side_effect=self.fake_generate), \
             mock.patch("services.router.generate", side_effect=self.fake_generate):
            res = self.client.post("/chat", json={"conversation_id": self.cid, "message": message})
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()

    def saved(self):
        return self.client.get(f"/conversations/{self.cid}").get_json()

    def test_switch_uses_the_new_experts_instructions_and_the_shared_history(self):
        self.assertEqual(self.chat("What should we build first?")["reply"], "Answer from Ethan Walker")

        data = self.chat("Can Sarah join?")
        self.assertTrue(data["switch"])
        self.assertEqual(data["expert"]["name"], "Sarah Patel")
        self.assertEqual(data["reply"], "Answer from Sarah Patel")
        prompt = self.prompts[-1]
        self.assertTrue(prompt.lstrip().startswith("You are Sarah Patel, ExpertOS's AI Cyber Security Consultant"))
        self.assertIn("Your areas of expertise: Authentication, Authorization, OWASP, API Security.", prompt)
        self.assertNotIn("System Design, Scalability", prompt)           # Ethan's expertise didn't leak in
        self.assertIn("The user has just asked for you", prompt)
        self.assertIn("What should we build first?", prompt)            # earlier context available
        self.assertIn("Ethan Walker: Answer from Ethan Walker", prompt)

        # Later messages stay with Sarah.
        self.assertEqual(self.chat("How long should sessions last?")["reply"], "Answer from Sarah Patel")
        self.assertEqual(self.saved()["active_expert"], "Security Expert")

    def test_switching_back_restores_the_first_expert_without_reintroduction(self):
        self.chat("What should we build first?")
        self.chat("Can Sarah join?")
        data = self.chat("Let's go back to Ethan")
        self.assertEqual(data["expert"]["name"], "Ethan Walker")
        prompt = self.prompts[-1]
        self.assertTrue(prompt.lstrip().startswith("You are Ethan Walker"))
        self.assertIn("brought you back into this consultation", prompt)
        self.assertIn("Your areas of expertise: System Design, Scalability", prompt)
        self.assertIn("Sarah Patel: Answer from Sarah Patel", prompt)

    def test_many_switches_keep_roles_and_history_consistent(self):
        sequence = [
            ("Can Sarah join?", "Security Expert"),
            ("Thanks Sarah, now Alex what about indexes?", "Database Engineer"),
            ("And how should the tables be partitioned?", "Database Engineer"),
            ("Switch to Maya please", "Design Advisor"),
            ("Back to Ethan", "Software Architect"),
            ("Can Sarah review the database security?", "Security Expert"),
        ]
        for message, expected in sequence:
            data = self.chat(message)
            self.assertEqual(data["expert"]["name"], expert_manager.get_expert(expected)["name"], message)
            self.assertEqual(data["reply"], f"Answer from {data['expert']['name']}")

        messages = self.saved()["messages"]
        users = [m["message"] for m in messages if m.get("sender") == "user"]
        self.assertEqual(users, [m for m, _ in sequence])          # each message stored once
        # Every expert reply is attributed to the expert who wrote it.
        for m in messages:
            if m.get("sender") == "expert" and m["message"].startswith("Answer from "):
                self.assertEqual(m["message"], f"Answer from {m['expert']['name']}")
        self.assertEqual(self.saved()["active_expert"], "Security Expert")

    def test_reload_keeps_the_active_expert(self):
        self.chat("Can Alex join?")
        saved = self.saved()
        self.assertEqual(saved["active_expert"], "Database Engineer")
        self.assertEqual(saved["expert"]["name"], "Alex Morgan")
        joined = [m["message"] for m in saved["messages"] if m["type"] == "system"]
        self.assertEqual(joined, ["🗄 Alex Morgan joined the consultation."])

    def test_failed_switch_changes_nothing(self):
        from services.errors import AIServiceError, TIMEOUT
        with mock.patch("services.ai_provider.generate", side_effect=AIServiceError("down", TIMEOUT)):
            res = self.client.post("/chat", json={"conversation_id": self.cid, "message": "Can Sarah join?"})
        self.assertEqual(res.status_code, 503)
        saved = self.saved()
        self.assertEqual(saved["active_expert"], "Software Architect")
        self.assertEqual(saved["messages"], [])

    def test_router_suggestion_must_be_a_real_expert(self):
        with mock.patch("services.ai_provider.generate", return_value="Answer"), \
             mock.patch("services.router.generate",
                        return_value='{"switch": true, "next_expert": "Hacker Bob", "handoff": "x"}'):
            data = self.client.post("/chat", json={"conversation_id": self.cid,
                                                   "message": "What should we build first?"}).get_json()
        self.assertFalse(data["switch"])
        self.assertEqual(data["expert"]["name"], "Ethan Walker")

    def test_switch_works_when_the_primary_provider_fails(self):
        def failing(*args, **kwargs):
            raise TimeoutError("primary down")

        def backup(prompt, max_tokens=None, temperature=None, images=None):
            return "Backup answer from " + prompt.split("You are ", 1)[1].split(",", 1)[0]

        router = ProviderRouter()
        router.providers = [
            {"name": "Primary", "generate": failing, "enabled": True},
            {"name": "Backup", "generate": backup, "enabled": True},
        ]
        with mock.patch("providers.provider_router.provider_router", router), \
             mock.patch("providers.provider_router.metrics.record_ai_call"):
            res = self.client.post("/chat", json={"conversation_id": self.cid, "message": "Can Sarah join?"})
        data = res.get_json()
        self.assertTrue(data["switch"])
        self.assertEqual(data["reply"], "Backup answer from Sarah Patel")
        self.assertEqual(self.saved()["active_expert"], "Security Expert")


class ResolveSwitchTests(unittest.TestCase):

    def test_natural_language_requests(self):
        cases = [
            ("can i speak with maya chen", "Software Architect", ("switch", "Design Advisor")),
            ("Switch to Maya.", "Software Architect", ("switch", "Design Advisor")),
            ("Switch me to Ethan Walker.", "Design Advisor", ("switch", "Software Architect")),
            ("Switch back to Ethan.", "Design Advisor", ("switch", "Software Architect")),
            ("I need someone specialising in cybersecurity.", "Software Architect", ("switch", "Security Expert")),
            ("I need a cybersecurity expert.", "Software Architect", ("switch", "Security Expert")),
            ("Can I talk to a designer?", "Software Architect", ("switch", "Design Advisor")),
            ("Can another expert help me?", "Software Architect", ("clarify", None)),
            ("I would like to change my expert.", "Software Architect", ("clarify", None)),
            ("I want to consult a financial advisor.", "Software Architect", ("unavailable", None)),
            ("Let me talk to the marketing expert.", "Software Architect", ("unavailable", None)),
        ]
        for message, current, (action, expert) in cases:
            with self.subTest(message):
                decision = expert_manager.resolve_switch(message, current)
                self.assertEqual(decision["action"], action)
                if expert:
                    self.assertEqual(decision["expert"], expert)

    def test_ordinary_questions_are_not_switch_requests(self):
        for message in ["What database should I use?", "How do I secure my API?", "Explain your recommendation",
                        "talk to me about caching", "Should I talk to my team about microservices?",
                        "I need someone who can build this quickly", "We need a marketing strategy",
                        "What are the main risks?"]:
            with self.subTest(message):
                self.assertIsNone(expert_manager.resolve_switch(message, "Software Architect"))


def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines["data"])))
    return events


class ExpertRoomSwitchTests(unittest.TestCase):
    """The individual expert chat (Expert Room) switches experts in the app, not in the AI's words."""

    RECOMMENDATION = {"title": "T", "recommendation": "Modular monolith", "description": "D", "metrics": []}

    def setUp(self):
        _testenv.fresh_database()
        self.client = _testenv.client(app)
        with mock.patch("services.expert_recommendation.generate", return_value=json.dumps(self.RECOMMENDATION)):
            self.cid = self.client.post("/expert/recommend", json={
                "expert": "Software Architect", "answers": {"description": "Online clothing store"}}).get_json()["conversation_id"]
        self.prompts = []

    def fake_stream(self, prompt, **kwargs):
        self.prompts.append(prompt)
        name = prompt.split("You are ", 1)[1].split(",", 1)[0]
        yield f"Reply from {name}"

    def send(self, message, expert="Software Architect"):
        # The SSE body is generated lazily: read it while the AI is mocked.
        with mock.patch("services.ai_provider.stream", side_effect=self.fake_stream):
            res = self.client.post("/expert/chat/stream", json={
                "expert": expert, "conversation_id": self.cid, "message": message})
            return parse_sse(res.get_data(as_text=True))

    def saved(self):
        return self.client.get(f"/conversations/{self.cid}").get_json()

    def test_speak_with_maya_switches_and_maya_answers_with_her_persona(self):
        self.send("What are the main risks?")
        events = self.send("can i speak with maya chen")
        kinds = [e for e, _ in events]
        self.assertEqual(kinds[0], "switch")
        switch = events[0][1]
        self.assertEqual((switch["expert_key"], switch["expert"]["name"]), ("Design Advisor", "Maya Chen"))
        self.assertEqual(switch["notice"], "🎨 Maya Chen joined the conversation.")
        done = events[-1][1]
        self.assertEqual((done["expert_key"], done["reply"]), ("Design Advisor", "Reply from Maya Chen"))

        prompt = self.prompts[-1]
        self.assertTrue(prompt.lstrip().startswith("You are Maya Chen, ExpertOS's AI Senior Product Designer"))
        self.assertIn("Your areas of expertise: UI Design, UX, User Research, Accessibility.", prompt)
        self.assertIn("The user has just asked for you", prompt)
        self.assertIn("What are the main risks?", prompt)                 # earlier context kept
        self.assertIn("never say you will forward a request", prompt)

        saved = self.saved()
        self.assertEqual(saved["active_expert"], "Design Advisor")
        self.assertEqual([m["type"] for m in saved["messages"]], ["chat", "chat", "chat", "system", "chat"])

    def test_later_messages_and_switching_back(self):
        self.send("Switch to Maya")
        # The browser still names the room's expert; the saved active expert answers.
        done = self.send("How should the product page look?")[-1][1]
        self.assertEqual(done["reply"], "Reply from Maya Chen")
        events = self.send("Switch back to Ethan.")
        self.assertEqual(events[0][1]["expert_key"], "Software Architect")
        self.assertIn("brought you back into this consultation", self.prompts[-1])
        self.assertEqual(self.saved()["active_expert"], "Software Architect")

    def test_specialty_request_clarify_and_unavailable(self):
        events = self.send("I need a cybersecurity expert.")
        self.assertEqual(events[0][1]["expert_key"], "Security Expert")

        prompts_before = len(self.prompts)
        done = self.send("Can another expert help me?")[-1][1]
        self.assertIn("Which expert would you like to talk to?", done["reply"])
        done = self.send("I want to consult a financial advisor.")[-1][1]
        self.assertIn("ExpertOS doesn't have that kind of expert", done["reply"])
        self.assertIn("Ethan Walker (Senior Software Architect)", done["reply"])
        self.assertEqual(len(self.prompts), prompts_before)          # answered by the app, no AI call
        self.assertEqual(self.saved()["active_expert"], "Security Expert")

    def test_switch_changes_only_the_chat_role_not_the_room(self):
        self.send("Can I speak with Maya Chen?")
        saved = self.saved()
        # The room (expert_key) stays Ethan's; only the chatbot role changed.
        self.assertEqual((saved["expert_key"], saved["active_expert"]), ("Software Architect", "Design Advisor"))
        ethan_room = self.client.get("/conversations?expert=Software%20Architect").get_json()["conversations"]
        maya_room = self.client.get("/conversations?expert=Design%20Advisor").get_json()["conversations"]
        self.assertEqual([c["id"] for c in ethan_room], [self.cid])
        self.assertEqual(maya_room, [])

        # A conversation in Maya's own room is separate, and switching there
        # to Ethan doesn't touch Ethan's room conversation.
        with mock.patch("services.expert_recommendation.generate", return_value=json.dumps(self.RECOMMENDATION)):
            maya_cid = self.client.post("/expert/recommend", json={
                "expert": "Design Advisor", "answers": {"description": "Checkout design"}}).get_json()["conversation_id"]
        with mock.patch("services.ai_provider.stream", side_effect=self.fake_stream):
            res = self.client.post("/expert/chat/stream", json={
                "expert": "Design Advisor", "conversation_id": maya_cid, "message": "Switch to Ethan"})
            body = res.get_data(as_text=True)
        self.assertIn('"expert_key": "Software Architect"', body)
        maya_saved = self.client.get(f"/conversations/{maya_cid}").get_json()
        self.assertEqual((maya_saved["expert_key"], maya_saved["active_expert"]), ("Design Advisor", "Software Architect"))
        self.assertEqual(self.saved()["active_expert"], "Design Advisor")        # Ethan's room untouched

    def test_ordinary_question_does_not_switch(self):
        events = self.send("What database should I use?")
        self.assertNotIn("switch", [e for e, _ in events])
        self.assertEqual(events[-1][1]["reply"], "Reply from Ethan Walker")

    def test_failed_reply_does_not_switch(self):
        from services.errors import AIServiceError, TIMEOUT

        def failing(prompt, **kwargs):
            raise AIServiceError("down", TIMEOUT)
            yield  # pragma: no cover

        with mock.patch("services.ai_provider.stream", side_effect=failing):
            res = self.client.post("/expert/chat/stream", json={
                "expert": "Software Architect", "conversation_id": self.cid, "message": "Switch to Maya"})
            body = res.get_data(as_text=True)
        self.assertIn("event: error", body)
        saved = self.saved()
        self.assertEqual(saved["active_expert"], "Software Architect")
        self.assertEqual(saved["messages"], [])


if __name__ == "__main__":
    unittest.main()
