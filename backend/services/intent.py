"""
What kind of message the user sent, so the experts answer what was actually
said instead of treating every message as a consultation question.

classify() returns one of:
  greeting         "hi", "hello there", "good morning"
  small_talk       "how are you?", "nice to meet you"
  thanks           "thanks!", "thank you, that helps"
  acknowledgement  "ok", "got it", "makes sense"
  farewell         "bye", "see you"
  request          anything else: a question, a request, information, a challenge

Only short, purely social messages are classified as social. A greeting that
comes with a request ("hi, can you review my schema?") is a request. The
classification controls orchestration (no expert routing or hand-over, one
brief reply) and is passed to the AI as guidance; the reply itself is still
written by the AI.
"""
import re

SOCIAL_INTENTS = {"greeting", "small_talk", "thanks", "acknowledgement", "farewell"}

_ADDRESSEES = r"(?:\s+(?:there|all|everyone|everybody|team|folks|guys|experts?|panel|again|ethan|maya|alex|sarah|daniel|ryan))*"

_PATTERNS = [
    ("greeting", rf"(?:hi|hii+|hello|hey|heya|hiya|howdy|greetings|yo|namaste|hola|good\s+(?:morning|afternoon|evening|day)){_ADDRESSEES}"),
    ("small_talk", r"(?:how\s+are\s+(?:you|u|you\s+all|you\s+guys)(?:\s+doing)?(?:\s+today)?|how(?:'s|\s+is)\s+it\s+going"
                   r"|what'?s\s+up|sup|nice\s+to\s+meet\s+(?:you|u)(?:\s+all)?|pleased\s+to\s+meet\s+you"
                   r"|how\s+do\s+you\s+do|are\s+you\s+there)"),
    ("thanks", r"(?:thanks|thank\s+you|thank\s+u|thx|ty|many\s+thanks|much\s+appreciated|appreciate\s+it|cheers)"
               r"(?:\s+(?:so|very)\s+much)?(?:\s+(?:a\s+lot|again|all|everyone|for\s+(?:that|this|the\s+help|your\s+help|helping)))*"),
    ("acknowledgement", r"(?:ok|okay|k|kk|got\s+it|i\s+see|understood|sure|cool|great|nice|perfect|alright|all\s+right|fine"
                        r"|sounds\s+good|makes\s+sense|that\s+makes\s+sense|noted|good|awesome|right|yes|yeah|yep|no\s+problem)"),
    ("farewell", r"(?:bye|goodbye|good\s+bye|see\s+(?:you|ya)(?:\s+later)?|talk\s+(?:to\s+you\s+)?later|good\s+night|take\s+care)"),
]
_COMPILED = [(name, re.compile(rf"^{pattern}\b")) for name, pattern in _PATTERNS]

MAX_SOCIAL_WORDS = 10


def _normalise(message):
    text = (message or "").lower().strip()
    text = re.sub(r"[’`]", "'", text)
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify(message):
    text = _normalise(message)
    if not text:
        return "request"
    if len(text.split()) > MAX_SOCIAL_WORDS:
        return "request"

    found = []
    remaining = text
    # Consume social phrases from the start ("hi there, how are you, thanks").
    while remaining:
        for name, pattern in _COMPILED:
            match = pattern.match(remaining)
            if match:
                found.append(name)
                remaining = remaining[match.end():].strip()
                break
        else:
            return "request"   # something non-social is left: treat as a real request

    # The most conversational part decides how to reply.
    for preferred in ("small_talk", "greeting", "thanks", "farewell", "acknowledgement"):
        if preferred in found:
            return preferred
    return "request"


def is_social(message):
    return classify(message) in SOCIAL_INTENTS


GUIDANCE = {
    "greeting": "The user is greeting you. Greet them back warmly in one or two short sentences and invite "
                "them to say what they'd like help with.",
    "small_talk": "The user is making small talk. Reply naturally and briefly (one or two sentences), then "
                  "invite them to share what they'd like to work on.",
    "thanks": "The user is thanking you. Acknowledge it briefly and offer further help in one sentence.",
    "acknowledgement": "The user is acknowledging what was said. Reply in one short sentence; offer the "
                       "natural next step or ask if they have questions. Don't repeat earlier advice.",
    "farewell": "The user is saying goodbye. Say goodbye briefly and warmly in one sentence.",
}

SOCIAL_RULES = (
    "This message is conversational, not a consultation question. Do NOT analyse the project, give "
    "technical advice, summarise anything, hand over to another expert or say 'Good question'. "
    "Keep it under 40 words."
)


def guidance(intent):
    """Prompt text describing how to reply to a message of this intent."""
    if intent in SOCIAL_INTENTS:
        return f"{GUIDANCE[intent]} {SOCIAL_RULES}"
    return (
        "The user is asking for help, giving information, or responding to the discussion. Work out exactly "
        "what they are asking and answer that directly. If they push back or disagree, engage with their "
        "objection and explain your reasoning."
    )
