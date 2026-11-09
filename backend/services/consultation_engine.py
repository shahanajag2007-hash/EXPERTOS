"""
Start Consultation: an analysis followed by a follow-up chat in which the
best-suited expert answers (and hands over to another expert when needed).

Each consultation is a saved conversation (services/conversations.py), so
several people can consult at once, and a consultation survives page reloads
and server restarts.
"""
import concurrent.futures

from services import conversations, intent
from services.expert_manager import expert_manager
from services.router import router
from services.ai_provider import ask_ai

# Runs the routing decision and the current expert's answer side by side.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="consultation")

FIRST_EXPERT = "Software Architect"


class ConsultationEngine:

    def start_consultation(self, owner, project, analysis, consultation_id=None):
        conversation_id = conversations.create(
            owner, "quick_consultation", FIRST_EXPERT, project=project,
            report=analysis, consultation_id=consultation_id, title=project,
        )
        return {
            "expert": expert_manager.get_expert(FIRST_EXPERT),
            "analysis": analysis,
            "conversation_id": conversation_id,
        }

    @staticmethod
    def _answer(row, expert_key, history, message, files, joined=False):
        return ask_ai(
            expert=expert_manager.get_expert(expert_key),
            project=row["project"],
            analysis=conversations.detail(row)["report"] or {},
            history=history,
            question=message,
            expert_key=expert_key,
            request_type="consultation_chat",
            files=files,
            joined=joined,
        )

    def chat(self, row, message, files=None, file_ids=None):
        """
        Answer one message in the consultation `row`. Messages are saved only
        once the answer exists, so a failure never stores a half exchange.
        """
        current_name = row["active_expert"]
        user_message = {"type": "chat", "sender": "user", "message": message}
        history = conversations.messages(row["id"]) + [user_message]
        user_item = ("user", None, message, file_ids)

        # Greetings, thanks and other social messages need no routing: the
        # current expert answers, unless the user greets another expert by
        # name ("Hi Maya"), who then joins without a hand-over speech.
        if intent.is_social(message):
            named = expert_manager.named_expert(message)
            if named and named != current_name:
                return self._switch(row, current_name, named, history, user_item, message, files, handoff=None)
            reply = self._answer(row, current_name, history, message, files)
            conversations.add_messages(row["id"], [user_item, ("expert", current_name, reply, None)])
            return {
                "switch": False,
                "expert": expert_manager.get_expert(current_name),
                "reply": reply,
                "history": conversations.messages(row["id"]),
            }

        # An explicit request ("Can Sarah join?") switches immediately; no AI
        # routing call is needed. Names win over topic words, and a topic in
        # the current expert's area keeps the current expert.
        manual = expert_manager.find_manual_request(message, current=current_name)

        # Requests phrased by specialty ("I need a cybersecurity expert"),
        # unclear ones ("can another expert help?") and requests for experts
        # ExpertOS doesn't have are resolved the same way as in the Expert Room.
        decision = expert_manager.resolve_switch(message, current_name)
        direct = decision and expert_manager.switch_reply(decision, current_name)
        if direct:
            conversations.add_messages(row["id"], [user_item, ("expert", current_name, direct, None)])
            return {
                "switch": False,
                "expert": expert_manager.get_expert(current_name),
                "reply": direct,
                "history": conversations.messages(row["id"]),
            }
        if decision and decision["action"] == "switch" and not manual:
            manual = decision["expert"]

        if manual and manual != current_name:
            route = {"switch": True, "next_expert": manual, "handoff": ""}
        elif manual == current_name:
            # Explicitly addressed (or squarely in their area): no routing call.
            reply = self._answer(row, current_name, history, message, files)
            conversations.add_messages(row["id"], [user_item, ("expert", current_name, reply, None)])
            return {
                "switch": False,
                "expert": expert_manager.get_expert(current_name),
                "reply": reply,
                "history": conversations.messages(row["id"]),
            }
        else:
            # The routing decision and the current expert's answer don't depend
            # on each other, so run them concurrently. If routing decides to
            # switch, the speculative answer is discarded. This roughly halves
            # the wait in the common no-switch case.
            route_future = _executor.submit(
                router.route,
                current_expert=current_name,
                project=row["project"],
                history=history,
                message=message,
            )
            answer_future = _executor.submit(self._answer, row, current_name, history, message, files)

            try:
                route = route_future.result()
            except Exception as exc:
                # Routing is an optimisation; if it fails, stay with the current expert.
                print(f"[Consultation] Routing failed, keeping {current_name}: {exc}")
                route = {"switch": False}

            if not route.get("switch") or route.get("next_expert") == current_name:
                reply = answer_future.result()
                conversations.add_messages(row["id"], [user_item, ("expert", current_name, reply, None)])
                return {
                    "switch": False,
                    "expert": expert_manager.get_expert(current_name),
                    "reply": reply,
                    "history": conversations.messages(row["id"]),
                }

        next_name = route["next_expert"]
        new_expert = expert_manager.get_expert(next_name)
        handoff = route.get("handoff") or f"I'd like {new_expert['name']} to take over from here."
        return self._switch(row, current_name, next_name, history, user_item, message, files, handoff)

    def _switch(self, row, current_name, next_name, history, user_item, message, files, handoff):
        """
        Make next_name the active expert and answer as them. The previous
        expert's optional hand-over line, the join notice, the user's message
        and the new expert's answer are saved together, and the active expert
        is updated in the same write, so the frontend and backend agree.
        """
        if not expert_manager.expert_exists(next_name):
            raise ValueError(f"Unknown expert {next_name!r}")
        current = expert_manager.get_expert(next_name)
        joined = f"{current['emoji']} {current['name']} joined the consultation."

        extra = ([{"type": "chat", "sender": "expert", "expert": expert_manager.get_expert(current_name),
                   "message": handoff}] if handoff else [])
        handover_history = history + extra + [{"type": "system", "message": joined}]
        answer = self._answer(row, next_name, handover_history, message, files, joined=True)

        conversations.add_messages(
            row["id"],
            [user_item]
            + ([("expert", current_name, handoff, None)] if handoff else [])
            + [("system", None, joined, None), ("expert", next_name, answer, None)],
            active_expert=next_name,
        )

        return {
            "switch": True,
            "expert": current,
            "reply": answer,
            "history": conversations.messages(row["id"]),
        }


consultation_engine = ConsultationEngine()
