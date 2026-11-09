import json

from providers.provider_router import generate
from services.context import format_history
from services.expert_manager import expert_manager


class ConsultationRouter:

    def route(
        self,
        current_expert,
        project,
        history,
        message
    ):

        # Highest priority → User explicitly requests an expert

        manual = expert_manager.find_manual_request(message, current=current_expert)

        if manual and manual != current_expert:

            return {
                "switch": True,
                "next_expert": manual,
                "reason": "User requested another consultant.",
                "handoff": ""
            }

        experts = "\n".join(
            [
                f"- {name}"
                for name in expert_manager.get_all_experts().keys()
            ]
        )

        # Recent messages in full, earlier ones condensed (services/context.py).
        conversation = format_history(history)

        prompt = f"""
You are the ExpertOS Consultation Router.

You NEVER answer technical questions.

You ONLY decide who should continue the consultation.

Current Expert:
{current_expert}

Available Experts:
{experts}

Project:
{project}

Conversation:
{conversation}

Latest User Message:
{message}

Return ONLY valid JSON.

{{
    "switch": true or false,
    "next_expert": "<expert name>",
    "reason": "<short reason>",
    "handoff": "<one natural sentence the current expert would say before leaving>"
}}

Rules:

- Default to switch=false. The current expert continues unless the latest
  message clearly needs a different specialty that the current expert can't
  reasonably cover.
- Greetings, thanks, small talk, acknowledgements and follow-ups on what the
  current expert just said never need a switch.
- If the user explicitly requested an expert, always switch. Mentioning an
  expert in passing ("Ethan said...", "do you agree with Alex?") is not a
  request.
- Never invent expert names.
"""

        text = generate(prompt, max_tokens=300, request_type="routing", expert_key=current_expert)

        if text.startswith("```"):
            text = (
                text.replace("```json", "")
                .replace("```", "")
                .strip()
            )

        try:

            result = json.loads(text)

        except Exception:

            result = {
                "switch": False,
                "next_expert": current_expert,
                "reason": "",
                "handoff": ""
            }

        if (
            result.get("next_expert")
            not in expert_manager.get_all_experts()
        ):

            result["switch"] = False
            result["next_expert"] = current_expert

        return result


router = ConsultationRouter()