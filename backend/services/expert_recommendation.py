from providers.provider_router import generate
from services import context
from services.errors import AIResponseError

import json


def generate_recommendation(expert, answers, files=None):
    from services.ai_provider import images_for

    prompt = f"""
You are a senior {expert}.

You are reviewing a software project.

Project Information:

{json.dumps(answers, indent=2)}

{context.documents_section(files)}

Return ONLY valid JSON.

Schema:

{{
    "title":"",
    "recommendation":"",
    "description":"",
    "metrics":[
        {{
            "name":"",
            "value":""
        }},
        {{
            "name":"",
            "value":""
        }},
        {{
            "name":"",
            "value":""
        }}
    ]
}}

Rules:

- Recommendation must match the expert.
- Description should be 120-180 words.
- Return exactly three metrics: the three most important things the team
  should measure to judge whether the recommendation works. "name" is the
  metric; "value" is a short qualitative target (e.g. "Under 200 ms at peak").
  Never present estimates as measured results and never invent before/after
  numbers, percentages or confidence scores.
- No markdown.
"""

    text = generate(prompt, request_type="recommendation", expert_key=expert, images=images_for(files))

    if text.startswith("```"):

        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:

        text = text[start:end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"[Recommendation] Unparseable response: {text}")
        raise AIResponseError(
            "The recommendation came back in an unreadable format. Please try again."
        ) from exc

    if not isinstance(data, dict) or not data.get("recommendation"):
        raise AIResponseError(
            "The recommendation was incomplete. Please try again."
        )

    # Normalise the shape the frontend renders.
    metrics = data.get("metrics")
    data["metrics"] = [
        {"name": str(m.get("name", "")), "value": str(m.get("value", ""))}
        for m in (metrics if isinstance(metrics, list) else [])
        if isinstance(m, dict) and m.get("name")
    ]

    # A model-generated confidence figure isn't a measurement; never pass one on.
    data.pop("confidence", None)

    for key in ("title", "recommendation", "description"):
        value = data.get(key, "")
        data[key] = value if isinstance(value, str) else json.dumps(value)

    return data
