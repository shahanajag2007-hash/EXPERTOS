import os
from dotenv import load_dotenv

load_dotenv()

# ─── TLS ─────────────────────────────────────────────────────────────────────
# Verify HTTPS certificates against the operating system's trust store instead
# of Python's bundled certifi list. Verification stays fully enabled; this only
# changes *which* trusted roots are used. It is needed when antivirus or a
# corporate proxy inspects HTTPS (e.g. Avast Web/Mail Shield), because those
# tools install their root certificate in the OS store, not in certifi.
# Must run before any HTTP client (OpenAI, Groq, requests) is created, which is
# why it lives here: every provider imports config first.
USE_SYSTEM_CERTIFICATES = os.getenv("USE_SYSTEM_CERTIFICATES", "true").lower() != "false"

if USE_SYSTEM_CERTIFICATES:
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        print(
            "[config] truststore is not installed; using Python's bundled certificates. "
            "Run `pip install -r requirements.txt` if HTTPS requests fail with "
            "CERTIFICATE_VERIFY_FAILED."
        )

# ─── Credentials (never sent to the frontend or logged) ──────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Groq model used when the router falls back to Groq.
GROQ_MODEL = os.getenv("GROQ_MODEL", "").strip() or "openai/gpt-oss-120b"

OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434"
)

# ─── OpenRouter model routing ────────────────────────────────────────────────
# Comma-separated model IDs, tried in order. Leave unset to use the defaults in
# services/openrouter_client.py.
OPENROUTER_MODELS = [
    m.strip()
    for m in os.getenv("OPENROUTER_MODELS", "").split(",")
    if m.strip()
]

# Image-capable OpenRouter models, tried in order when a request includes
# images (uploaded screenshots). Leave unset for the defaults.
OPENROUTER_VISION_MODELS = [
    m.strip()
    for m in os.getenv("OPENROUTER_VISION_MODELS", "").split(",")
    if m.strip()
]

# Reasoning for models that support it: off | low | medium | high.
# Off by default: reasoning tokens count against max_tokens, and with it on
# the free reasoning models spent whole budgets thinking and returned no answer.
OPENROUTER_REASONING = os.getenv("OPENROUTER_REASONING", "off").strip().lower()

MODEL = "google/gemini-2.5-flash"

MAX_TOKENS = 1500

TEMPERATURE = 0.3
