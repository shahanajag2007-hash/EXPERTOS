"""
Understanding what the user actually said: greetings and other social
messages get a brief, natural reply instead of a project review or an expert
hand-over. AI calls are mocked.

Run from the backend directory:
    python -m unittest discover -s tests -v
"""
import _testenv  # noqa: F401  (must come before app imports)
import json
import unittest
from unittest import mock

from app import app
from services import intent
from services.ai_provider import build_chat_prompt
from services.expert_manager import expert_manager

ANALYSIS = {"architecture": "Monolith.", "recommendation": "Start small."}


class ClassifierTests(unittest.TestCase):

    def test_social_messages(self):
        cases = {
            "hi": "greeting", "Hi.": "greeting", "Hey there team!": "greeting",
            "good morning experts": "greeting", "Hello, how are you?": "small_talk",
            "nice to meet you": "small_talk", "thanks!": "thanks",
            "Thank you so much for the help": "thanks", "got it, thanks": "thanks",
            "ok": "acknowledgement", "makes sense": "acknowledgement", "bye": "farewell",
        }
        for message, expected in cases.items():
            with self.subTest(message):
                self.assertEqual(intent.classify(message), expected)

    def test_requests_are_not_mistaken_for_social(self):
        for message in [
            "hi, can you review my schema?", "I need help understanding my project.",
            "Can you analyse my business strategy?", "how are you handling auth?", "ok but why not mongo?",
            "Which of your recommendations should I prioritise first, and why?",
            "I disagree with this recommendation. Can you explain why this is better than the alternative?",
            "yes please explain", "",
        ]:
            with self.subTest(message):
                self.assertEqual(intent.classify(message), "request")


class ChatPromptTests(unittest.TestCase):

    def setUp(self):
        self.expert = expert_manager.get_expert("Software Architect")

    def test_greeting_prompt_asks_for_a_brief_greeting(self):
        prompt = build_chat_prompt(self.expert, "A booking app", ANALYSIS, [], "hi")
        self.assertIn("The user is greeting you", prompt)
        self.assertIn("Do NOT analyse the project", prompt)
        self.assertIn("Keep it short and conversational", prompt)

    def test_prompt_no_longer_teaches_stock_phrases_or_false_claims(self):
        prompt = build_chat_prompt(self.expert, "A booking app", ANALYSIS, [], "How should I scale?")
        self.assertNotIn('say\n\n"Good question."', prompt)
        self.assertIn('Don\'t open with stock phrases such as "Good question"', prompt)
        self.assertNotIn("Mention that you've reviewed the previous discussion", prompt)
        self.assertIn("This is your first reply in this conversation.", prompt)
        self.assertIn("Never claim to have reviewed documents", prompt)
        self.assertNotIn("the attached files (below)", prompt)

    def test_hand_over_is_stated_only_when_it_happened(self):
        joined = build_chat_prompt(self.expert, "p", ANALYSIS, [], "Can Ethan join?", joined=True)
        self.assertIn("The user has just asked for you", joined)
        history = [{"type": "chat", "sender": "expert", "expert": self.expert, "message": "Earlier"}]
        later = build_chat_prompt(self.expert, "p", ANALYSIS, history, "And then?")
        self.assertIn("You have already spoken", later)
        self.assertNotIn("The user has just asked for you", later)


class ConsultationRoutingTests(unittest.TestCase):

    def setUp(self):
        _testenv.fresh_database()
        self.client = _testenv.client(app)
        with mock.patch("services.ai_provider.generate", return_value=json.dumps(ANALYSIS)):
            self.conversation = self.client.post("/analyze", json={"prompt": "A booking app"}).get_json()["conversation_id"]

    def test_greeting_is_answered_by_the_current_expert_without_routing(self):
        with mock.patch("services.consultation_engine.ask_ai", return_value="Hello! What can I help with?") as ask, \
             mock.patch("services.router.generate") as router:
            res = self.client.post("/chat", json={"conversation_id": self.conversation, "message": "Hi"})
        data = res.get_json()
        router.assert_not_called()
        self.assertFalse(data["switch"])
        self.assertEqual(data["expert"]["name"], "Ethan Walker")
        self.assertEqual(ask.call_count, 1)
        self.assertEqual([m["message"] for m in data["history"]], ["Hi", "Hello! What can I help with?"])

    def test_greeting_another_expert_by_name_brings_them_in_without_a_hand_over_speech(self):
        with mock.patch("services.consultation_engine.ask_ai", return_value="Hi!"), \
             mock.patch("services.router.generate") as router:
            data = self.client.post("/chat", json={"conversation_id": self.conversation,
                                                   "message": "hello Sarah"}).get_json()
        router.assert_not_called()
        self.assertTrue(data["switch"])
        self.assertEqual(data["expert"]["name"], "Sarah Patel")
        # No "I'd like Sarah to take over" line: just the join notice and Sarah's reply.
        self.assertEqual([m["type"] for m in data["history"]], ["chat", "system", "chat"])

    def test_real_questions_still_route(self):
        with mock.patch("services.consultation_engine.ask_ai", return_value="Answer"), \
             mock.patch("services.router.generate", return_value='{"switch": false}') as router:
            self.client.post("/chat", json={"conversation_id": self.conversation,
                                            "message": "How should we deploy this?"})
        router.assert_called_once()

    def test_handed_over_expert_is_told_it_joined(self):
        with mock.patch("services.consultation_engine.ask_ai", return_value="Security view.") as ask:
            self.client.post("/chat", json={"conversation_id": self.conversation, "message": "Can Sarah join?"})
        self.assertTrue(ask.call_args.kwargs["joined"])


if __name__ == "__main__":
    unittest.main()
