import json

from providers.provider_router import generate


def get_technology(project, technology, expert):

    prompt = f"""
You are {expert}.

You are explaining technology during a live consultation.

Return ONLY valid JSON.

Schema:

{{
    "title": "",
    "expert": "{expert}",
    "pages": [
        {{
            "title": "",
            "content": ""
        }}
    ]
}}

Rules:

- Return exactly 6 pages.
- Every page must have title and content.
- Content should be 120–180 words.
- Never use bullet points.
- Speak naturally like an experienced consultant.
- Relate every explanation to THIS project.
- Do not explain like Wikipedia.

Create these pages exactly in this order:

1. 📘 What is {technology}?

2. ⭐ Why I Recommended It

3. 🛠 How I'd Use It In This Project

4. ⚖ Comparison

5. ⚠ Mistakes I See Often

6. 🔗 Learn Next

Project:

{project}
"""

    text = generate(prompt, request_type="knowledge")

    if text.startswith("```"):
        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

    try:

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:
            text = text[start:end + 1]

        return json.loads(text)

    except Exception as e:

        print(f"[knowledge_service] JSON parse error for technology='{technology}': {e}")
        return {
            "title": technology,
            "expert": expert,
            "pages": [
                {
                    "title": "Unable to load",
                    "content": "ExpertOS couldn't generate this explanation."
                }
            ]
        }