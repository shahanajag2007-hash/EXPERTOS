import json
from providers.provider_router import generate, stream
from services import context, intent
from services.errors import AIResponseError

def images_for(files):
    """Image attachments for the AI from uploaded_files rows."""
    from services.files import image_bytes

    return [{"mime": row["content_type"], "data": image_bytes(row)}
            for row in files or [] if row["kind"] == "image"]


def analyze_project(project, files=None):

    prompt = f"""
    You are a Senior Software Architect.

    Analyze the following software project.

    Return ONLY valid JSON.

    Return EXACTLY this schema:

    {{
        "architecture": "",
        "tech_stack": "",
        "database": "",
        "security": "",
        "deployment": "",
        "recommendation": ""
    }}

    Rules:

    - Fill ALL six fields.
    - Never leave any field empty.
    - Every value MUST be a string.
    - Do NOT return nested objects.
    - Do NOT return arrays.
    - Do NOT create additional keys.
    - Return ONLY valid JSON.
    - Do NOT wrap the JSON inside markdown.

    Content Rules:

    - Each field should contain ONLY 2 or 3 complete sentences.
    - Write naturally like a senior software architect.
    - Do NOT use keywords.
    - Do NOT use bullet points.
    - Explain WHAT you recommend.
    - Explain WHY you recommend it.
    - If information is missing, infer the best industry practice.
    - Do NOT repeat the same explanation across multiple fields.

    Focus of each field:

    Architecture:
    Explain the recommended software architecture and why it suits the project.

    Tech Stack:
    Explain why the selected frameworks, languages and tools fit the project.

    Database:
    Recommend the most suitable database and explain why.

    Security:
    Explain the most important security measures this project should implement.

    Deployment:
    Recommend how the application should be deployed and scaled.

    Recommendation:
    Provide your overall opinion and the next steps for the project.

    Project:

    {project}

    {context.documents_section(files)}
    """

    # Six fields of 2-3 sentences need ~600 tokens. A truncated answer is
    # retried once with double the budget (see openrouter_client), so a large
    # default budget isn't needed.
    text = generate(
        prompt,
        max_tokens=1500,
        temperature=0.2,
        request_type="consultation_analysis",
        expert_key="Software Architect",
        images=images_for(files),
    )
    if text is None:
        raise Exception("generate() returned None")
    print("========== RAW RESPONSE ==========")
    print(text)
    print("==================================")
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

        data = json.loads(text)

        for key in [
            "architecture",
            "tech_stack",
            "database",
            "security",
            "deployment",
            "recommendation"
        ]:

            value = data.get(key, "")

            if not isinstance(value, str):
                value = json.dumps(value, indent=2)

            data[key] = value

        return data

    except Exception as e:

        print("========== PARSE ERROR ==========")
        print(e)
        print(text)
        print("================================")

        raise AIResponseError(
            "The expert's analysis came back in an unreadable format. Please try again."
        ) from e


# Long conversations are condensed rather than cut off: see services/context.py.


def ask_ai(
    expert,
    project,
    analysis,
    history,
    question,
    expert_key=None,
    request_type="expert_chat",
    files=None,
    joined=False,
):
    return generate(
        build_chat_prompt(expert, project, analysis, history, question, files, joined),
        request_type=request_type,
        expert_key=expert_key,
        images=images_for(files),
    )


def stream_ai(expert, project, analysis, history, question, expert_key=None,
              request_type="expert_chat", timer=None, files=None, joined=False):
    """Like ask_ai, but yields the reply as text chunks."""
    return stream(
        build_chat_prompt(expert, project, analysis, history, question, files, joined),
        request_type=request_type,
        expert_key=expert_key,
        timer=timer,
        images=images_for(files),
    )


def _roster():
    from services.expert_manager import expert_manager
    return expert_manager.describe(list(expert_manager.get_all_experts()))


def build_chat_prompt(
    expert,
    project,
    analysis,
    history,
    question,
    files=None,
    joined=False,
):
    """
    Prompt for one expert reply. The reply depends on what the user actually
    said (services/intent.py): a greeting gets a greeting, not a project
    review. The prompt only refers to material that really exists: earlier
    messages, the report/analysis, and attached files.
    """
    kind = intent.classify(question)
    social = kind in intent.SOCIAL_INTENTS
    conversation = context.format_history(history)
    documents = context.documents_section(files)
    spoken_before = any(
        isinstance(m, dict) and m.get("sender") == "expert"
        and (m.get("expert") or {}).get("name") == expert["name"]
        for m in history or []
    )

    # joined="returning": the user switched back to an expert who was already
    # part of this conversation (e.g. the Expert Room's own expert).
    if joined and (spoken_before or joined == "returning"):
        situation = (
            "The user has just brought you back into this consultation; other experts spoke since your "
            "last reply. Don't introduce yourself again. Respond to the user's latest message, building on "
            "the conversation above, including what the other experts said."
        )
    elif joined:
        situation = (
            "The user has just asked for you, so you are now the expert in this consultation. "
            "Introduce yourself in one short sentence, then respond to their latest message from your "
            "specialty: if it was only a request for you, offer your help with their project in your "
            "area. You may say you've read the conversation above, because you have."
        )
    elif spoken_before:
        situation = "You have already spoken in this conversation. Continue naturally; don't introduce yourself again."
    else:
        situation = "This is your first reply in this conversation."

    material = []
    if conversation.strip():
        material.append("the conversation so far (below)")
    if analysis:
        material.append("the project summary/report already shown to the user (below)")
    if files:
        material.append("the attached files (below)")
    material_line = (
        "You have: " + ", ".join(material) + "."
        if material else "There is no earlier discussion, report or attached file."
    )

    expertise = ", ".join(expert.get("expertise") or [])

    return f"""
You are {expert["name"]}, ExpertOS's AI {expert["role"]} persona, giving a consultation to a
software developer. Speak with the judgement of an experienced {expert["role"]}: natural,
confident, concise, like a senior mentor talking to a colleague.
{f"Your areas of expertise: {expertise}." if expertise else ""}
Earlier messages may be from other ExpertOS experts; they spoke for themselves. You are only
{expert["name"]} now: answer from your own specialty, not theirs.

You are one of ExpertOS's AI experts: {_roster()}. ExpertOS itself switches
the user to another expert when they ask for one. Don't bring up switching. Only if the user
asks you for a different expert, tell them to ask ExpertOS to switch (e.g. "Switch to Maya");
never say you will forward a request, pass a message on, or can't connect them.

Stay in character as this specialist and don't add generic AI disclaimers, but never claim to
be a human. If asked, say you are an AI expert. Never mention which AI model or provider powers you.

-----------------------------------------
WHAT THE USER JUST SAID

{question}

HOW TO RESPOND TO IT

{intent.guidance(kind)}

-----------------------------------------
YOUR SITUATION

{situation}

{material_line}
Only refer to material listed here. Never claim to have reviewed documents, files or
information that isn't shown below.

-----------------------------------------
PROJECT (background)

{project or "(No project description was given.)"}

PROJECT SUMMARY / REPORT ALREADY SHOWN TO THE USER (background only; don't repeat it)

{json.dumps(analysis, indent=2) if analysis else "(none)"}

{documents}

-----------------------------------------
CONVERSATION SO FAR (oldest first)

{conversation or "(This is the start of the conversation.)"}

-----------------------------------------
REPLY RULES

1. Answer only the user's latest message, using the conversation for context.
2. {"Keep it short and conversational." if social else "Answer from your specialty with practical, specific advice for this project. If the question is outside your area, answer briefly from your perspective and say which expert would know more."}
3. Don't open with stock phrases such as "Good question", "Great question", "Certainly" or
   "Absolutely". Start with the substance.
4. Write naturally in prose; use bullet points only when a list genuinely helps.
5. Ask a follow-up question only if the latest message can't reasonably be answered without it.
6. If you disagree with something said earlier, say so politely and explain why.
7. Never write lines for the user or for another expert.
"""
