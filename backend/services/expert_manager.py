import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

with open(BASE_DIR / "data" / "experts.json", encoding="utf-8") as file:
    experts = json.load(file)


# Words that mean the user is explicitly asking for an expert.
# Matched as whole words, so "ui" does not match "build" or "quick".
ALIASES = {

    "Software Architect": [
        "ethan",
        "architect",
        "software architect",
        "architecture expert"
    ],

    "Design Advisor": [
        "maya",
        "designer",
        "design advisor",
        "ui",
        "ux",
        "figma"
    ],

    "Database Engineer": [
        "alex",
        "database",
        "db",
        "sql",
        "postgres",
        "postgresql",
        "mysql",
        "mongodb"
    ],

    "Security Expert": [
        "sarah",
        "security",
        "cyber security",
        "authentication",
        "jwt",
        "authorization"
    ],

    "Cloud Consultant": [
        "daniel",
        "cloud",
        "aws",
        "azure",
        "deployment"
    ],

    "DevOps Engineer": [
        "ryan",
        "devops",
        "docker",
        "kubernetes",
        "ci cd",
        "pipeline"
    ]

}

# How users refer to a specific expert as a person: first name, full name or
# role title. These take priority over topic words when deciding who the user
# is asking for (see find_manual_request).
PEOPLE = {
    key: [
        expert["name"].split(" ")[0].lower(),
        expert["name"].lower(),
        key.lower(),
    ] + {
        "Software Architect": ["architect", "architecture expert"],
        "Design Advisor": ["designer"],
        "Database Engineer": ["database expert", "db expert", "dba"],
        "Security Expert": ["security consultant"],
        "Cloud Consultant": ["cloud expert", "cloud architect"],
        "DevOps Engineer": ["devops expert"],
    }.get(key, [])
    for key, expert in experts.items()
}

# Words just before a name that mean "this is who I want to talk to now".
INVITATION_BEFORE = (
    r"(?:can|could|let|ask|bring(?:\s+in)?|get|invite|call|switch\s+(?:back\s+)?to|go\s+back\s+to"
    r"|back\s+to|talk\s+to|speak\s+(?:to|with)|over\s+to|hand\s+(?:it\s+)?(?:over\s+)?to|now|want|need)$"
)
# Words just after a name that ask that expert to step in ("Sarah, join us").
INVITATION_AFTER = (
    r"(?:(?:can|could|would|will)\s+you\s+|please\s+)?(?:join|take\s+over|come\s+(?:in|back)|step\s+in"
    r"|help|review|take\s+a\s+look|look\s+at|weigh\s+in|jump\s+in)\b"
)
# Words before a name that only address that expert ("Sarah, what ...").
ADDRESS_BEFORE = r"^(?:hi|hello|hey|ok|okay|so|thanks?|thank\s+you|great|cool)?$"

# Phrases that ask for a (different) expert, e.g. "can I speak with",
# "switch me to", "I need someone specialising in", "can another expert help".
SWITCH_REQUEST = (
    r"\b(?:speak|talk|chat)\s+(?:with|to)\s+(?!me\b|us\b|my\b|our\b|you\b|them\b|him\b|her\b)"
    r"|\bswitch\s+(?:me\s+)?(?:back\s+)?to\b|\bswitch\s+(?:the\s+)?experts?\b"
    r"|\bchange\s+(?:my\s+|the\s+)?(?:expert|consultant|advisor)\b|\b(?:another|different|other)\s+(?:expert|consultant|specialist|advisor)\b"
    r"|\bconnect\s+me\b|\btransfer\s+me\b|\bhand\s+me\s+over\b|\bbring\s+in\b|\bback\s+to\b"
    r"|\b(?:want|need|like|prefer)\s+(?:to\s+)?(?:consult|speak|talk)\b"
    r"|\b(?:want|need|like)\s+(?:an?\s+|the\s+)?(?:someone|somebody|expert|specialist|consultant|advisor)\b"
    r"|\b(?:want|need|like)\s+(?:an?|the)\s+[\w\s/-]{1,40}?\b(?:expert|specialist|consultant|advisor|engineer|designer|architect)\b"
    r"|\bconsult\s+(?:a|an|the|with)\b|\blet\s+me\s+(?:talk|speak)\b"
)
# A request for "another expert" without saying which one.
GENERIC_EXPERT_REQUEST = (
    r"\b(?:another|different|other)\s+(?:expert|consultant|specialist|advisor)\b"
    r"|\bchange\s+(?:my\s+|the\s+)?(?:expert|consultant|advisor)\b|\bswitch\s+(?:the\s+)?experts?\b"
)
# A request for a specific kind of expert ("a financial advisor", "the marketing expert").
ROLE_REQUEST = (
    r"\b(?:an?|the|some)\s+[\w/-]+(?:\s+[\w/-]+)?\s+(?:expert|specialist|consultant|advisor|adviser|engineer"
    r"|designer|architect|analyst|lawyer|accountant|marketer|strategist|coach|manager)\b"
    r"|\b(?:an?|the)\s+(?:lawyer|accountant|marketer|strategist|coach|doctor|therapist)\b"
)
# Specialties a user may ask for by description ("I need a cybersecurity expert").
SPECIALTIES = {
    "Software Architect": ["architecture", "architect", "software architect", "system design", "backend",
                           "scalability", "microservices"],
    "Design Advisor": ["design", "designer", "ui", "ux", "user experience", "user interface", "product design",
                       "product designer", "figma", "accessibility"],
    "Database Engineer": ["database", "databases", "db", "sql", "data modelling", "data modeling", "schema",
                          "postgres", "postgresql", "mysql", "mongodb"],
    "Security Expert": ["security", "cybersecurity", "cyber security", "infosec", "authentication",
                        "owasp", "penetration testing", "pentest", "secure"],
    "Cloud Consultant": ["cloud", "aws", "azure", "gcp", "hosting", "infrastructure", "cloud architecture"],
    "DevOps Engineer": ["devops", "ci/cd", "ci cd", "cicd", "pipeline", "pipelines", "docker", "kubernetes",
                        "automation", "monitoring"],
}

# Extra topic words used only when recommending an expert from a free-text
# problem description (the AI Guide). Aliases above are included as well.
TOPICS = {
    "Software Architect": [
        "architecture", "microservices", "monolith", "scalability", "scale",
        "api", "apis", "backend", "system design", "tech stack", "rest"
    ],
    "Design Advisor": [
        "user interface", "user experience", "usability", "accessibility",
        "layout", "onboarding", "wireframe", "design system"
    ],
    "Database Engineer": [
        "schema", "query", "queries", "index", "indexing", "nosql",
        "data model", "migration", "redis", "double booking", "double bookings",
        "race condition", "concurrency", "transaction", "transactions", "locking"
    ],
    "Security Expert": [
        "vulnerability", "encryption", "oauth", "login", "password",
        "owasp", "compliance", "gdpr", "xss", "csrf"
    ],
    "Cloud Consultant": [
        "gcp", "serverless", "hosting", "infrastructure", "terraform",
        "cloud cost", "region"
    ],
    "DevOps Engineer": [
        "ci/cd", "github actions", "monitoring", "automation", "deploy",
        "deploys", "container", "containers", "logging"
    ],
}

DEFAULT_EXPERT = "Software Architect"


def _contains_word(text, word):
    return re.search(
        rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])",
        text
    ) is not None


class ExpertManager:

    def get_expert(self, expert_name):

        return experts.get(expert_name)

    def get_all_experts(self):

        return experts

    def expert_exists(self, expert_name):

        return expert_name in experts

    def find_manual_request(self, message, current=None):
        """
        The expert the user is explicitly asking for, or None.

        People are matched before topics: an expert named by first name or
        role title wins over a topic word ("Can Sarah review the database?"
        is a request for Sarah). A named expert counts only when invited
        ("can Sarah join", "switch to Maya", "back to Ethan", "now Sarah ...",
        "Alex, take a look") or addressed at the start ("Sarah, what ...");
        the latest invitation wins. An expert mentioned in passing ("Ethan
        said ...") is not a request, and then topic words are ignored too.
        Topic words alone keep the current expert when they match the current
        expert's area.
        """
        text = message.lower()

        def first_position(words):
            hits = [m.start() for w in words
                    for m in re.finditer(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text)]
            return min(hits) if hits else None

        # Every mention of an expert: (start, end, expert), longest name first
        # so "sarah patel" isn't also counted as "sarah".
        mentions, taken = [], set()
        for expert in experts:
            for word in sorted(PEOPLE.get(expert, []), key=len, reverse=True):
                for m in re.finditer(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text):
                    if not taken & set(range(m.start(), m.end())):
                        mentions.append((m.start(), m.end(), expert))
                        taken.update(range(m.start(), m.end()))
        mentions.sort()

        if mentions:
            def before(start):
                # Text just before the name, without a trailing "the" ("switch to the architect").
                preceding = text[:start].strip(" ,.!?:;-")
                return re.sub(r"(?:^|\s)the$", "", preceding).strip(" ,.!?:;-")

            invited = [e for s, end, e in mentions
                       if re.search(INVITATION_BEFORE, before(s))
                       or re.match(INVITATION_AFTER, text[end:].strip(" ,.!:;-"))]
            if invited:
                return invited[-1]
            addressed = [e for s, _, e in mentions
                         if re.search(ADDRESS_BEFORE, before(s)) and not before(s).startswith("thank")]
            if addressed:
                return addressed[0]
            # Named only in passing ("Ethan said...", "agree with Ethan"): not a
            # request to switch. The AI router decides as usual.
            return None

        topics = [e for e, words in ALIASES.items() if first_position(words) is not None]
        if not topics:
            return None
        if current in topics:
            return current
        return min(topics, key=lambda e: first_position(ALIASES[e]))

    def resolve_switch(self, message, current):
        """
        Decide whether the user is asking to change experts, using only
        explicit requests (an ordinary question that mentions a topic is not a
        switch). Returns None, or one of:
          {"action": "switch", "expert": key}         exactly one expert fits
          {"action": "stay", "expert": key}           asked for the current expert
          {"action": "clarify", "options": [keys]}    several fit, or none named
          {"action": "unavailable"}                   asked for a kind of expert ExpertOS doesn't have
        """
        text = " ".join(message.lower().split())
        named = self.find_manual_request(message, current=current)
        if named is not None and any(_contains_word(text, w) for w in PEOPLE.get(named, [])):
            return {"action": "stay" if named == current else "switch", "expert": named}

        if not re.search(SWITCH_REQUEST, text):
            return None

        # "Switch me to Ethan Walker": a switch phrase plus exactly one named expert.
        people = [k for k in experts if any(_contains_word(text, w) for w in PEOPLE.get(k, []))]
        if len(people) == 1:
            return {"action": "stay" if people[0] == current else "switch", "expert": people[0]}

        wanted = [key for key, words in SPECIALTIES.items() if any(_contains_word(text, w) for w in words)]
        if len(wanted) == 1:
            return {"action": "stay" if wanted[0] == current else "switch", "expert": wanted[0]}
        if len(wanted) > 1:
            return {"action": "clarify", "options": wanted}
        if re.search(GENERIC_EXPERT_REQUEST, text):
            return {"action": "clarify", "options": [k for k in experts if k != current]}
        if re.search(ROLE_REQUEST, text):
            return {"action": "unavailable"}   # e.g. "a financial advisor": ExpertOS has none
        return None

    def describe(self, keys):
        return ", ".join(f"{experts[k]['name']} ({experts[k]['role']})" for k in keys)

    def switch_reply(self, decision, current):
        """The answer to a switch request that can't be carried out directly, or None."""
        if decision["action"] == "clarify":
            options = decision["options"]
            first = experts[options[0]]["name"].split(" ")[0]
            return (f"Which expert would you like to talk to? You can switch to {self.describe(options)}. "
                    f"Just say, for example, \"Switch to {first}\".")
        if decision["action"] == "unavailable":
            others = [k for k in experts if k != current]
            return ("ExpertOS doesn't have that kind of expert. The AI experts available are "
                    f"{self.describe(others)}. Tell me who you'd like to talk to, or keep asking me.")
        return None

    def named_expert(self, message):
        """The expert the message names by first name or role title, if exactly one."""
        text = message.lower()
        named = [e for e in experts if any(_contains_word(text, w) for w in PEOPLE.get(e, []))]
        return named[0] if len(named) == 1 else None

    def recommend(self, problem):
        """
        Pick the expert whose topics best match a problem description.

        Returns (expert_key, matched_words). matched_words is empty when
        nothing matched and the default expert was chosen.
        """
        text = problem.lower()

        best_key, best_matches = DEFAULT_EXPERT, []

        for expert in experts:
            words = ALIASES.get(expert, []) + TOPICS.get(expert, [])
            matches = [w for w in dict.fromkeys(words) if _contains_word(text, w)]

            if len(matches) > len(best_matches):
                best_key, best_matches = expert, matches

        return best_key, best_matches


expert_manager = ExpertManager()
