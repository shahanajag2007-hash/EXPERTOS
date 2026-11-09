"""
OpenRouter client with intelligent model routing, health tracking,
retry-with-backoff, and graceful degradation.

Failure handling per category (see services/errors.py):
  - provider-wide (TLS, connection, 401, 402, account quota): stop — every
    other model would fail the same way.
  - transient (5xx, connection blips): retry the same model with backoff.
  - model-specific (429 for one model, timeout, empty/malformed output,
    404, 403, 400): move on to the next model.
"""
import time
import threading
from openai import OpenAI
from config import (
    OPENROUTER_API_KEY, OPENROUTER_MODELS, OPENROUTER_VISION_MODELS, OPENROUTER_REASONING,
    MAX_TOKENS, TEMPERATURE,
)
import base64
from services.errors import (
    ProviderError, classify_exception, category_for_status, log_detail, PROVIDER_WIDE,
    retry_at_from_exception,
    CONNECTION, SERVER, RATE_LIMIT, TIMEOUT, EMPTY, MALFORMED,
    MODEL_NOT_FOUND, FORBIDDEN, BAD_REQUEST, NOT_CONFIGURED, UNKNOWN,
)

# ─── Custom Exceptions ────────────────────────────────────────────────────────

class ModelUnavailable(ProviderError):
    """Raised when a specific model is rate-limited or temporarily unavailable."""

class AllModelsExhausted(ProviderError):
    """Raised when every model in the registry has failed."""

# ─── Model Registry ───────────────────────────────────────────────────────────

# Ordered by preference: quality first, then fallbacks.
# Each entry can be added/removed without touching any other code.
# Verified against OpenRouter's /api/v1/models catalogue on 2026-11-09
# (nvidia/nemotron-3-super-120b-a12b:free had been retired); free model IDs
# are retired regularly, so override with OPENROUTER_MODELS in backend/.env
# (comma-separated) or check with scripts/check_ai_providers.py.
DEFAULT_MODEL_REGISTRY = [
    {
        "name":    "Gemma 4 31B",
        "id":      "google/gemma-4-31b-it:free",
        "tier":    "primary",
    },
    {
        "name":    "Gemma 4 26B A4B",
        "id":      "google/gemma-4-26b-a4b-it:free",
        "tier":    "secondary",
    },
    {
        "name":    "Nemotron 3.5 Lightning",
        "id":      "nvidia/nemotron-3.5-lightning:free",
        "tier":    "secondary",
    },
    {
        # OpenRouter's own router: picks any currently available free model.
        "name":    "OpenRouter Free Router",
        "id":      "openrouter/free",
        "tier":    "fallback",
    },
]

MODEL_REGISTRY = (
    [{"name": mid, "id": mid, "tier": "configured"} for mid in OPENROUTER_MODELS]
    if OPENROUTER_MODELS else DEFAULT_MODEL_REGISTRY
)

# Models used when a request includes images (they accept image input,
# checked against the same catalogue). Override with OPENROUTER_VISION_MODELS.
DEFAULT_VISION_MODELS = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "openrouter/free",
]
VISION_MODELS = OPENROUTER_VISION_MODELS or DEFAULT_VISION_MODELS

# Appended when a streamed answer reached the token limit, so a cut-off reply
# is never presented as complete.
TRUNCATION_NOTE = "\n\n_(This reply reached its length limit and was cut off. Ask me to continue.)_"

# ─── Health Tracker ───────────────────────────────────────────────────────────

_COOLDOWN_SECONDS     = 60    # how long to deprioritise a failing model
_MAX_FAILURES         = 2     # failures before cooldown
_UNAVAILABLE_SECONDS  = 1800  # retired (404) or restricted (403) models

class _ModelHealth:
    """Tracks per-model failure counts and cooldown windows."""

    def __init__(self):
        self._lock     = threading.Lock()
        self._failures = {}   # model_id → int
        self._cooldown = {}   # model_id → timestamp

    def is_healthy(self, model_id: str) -> bool:
        with self._lock:
            cooldown_until = self._cooldown.get(model_id, 0)
            if time.time() < cooldown_until:
                return False
            return True

    def record_failure(self, model_id: str):
        with self._lock:
            self._failures[model_id] = self._failures.get(model_id, 0) + 1
            if self._failures[model_id] >= _MAX_FAILURES:
                self._cooldown[model_id] = time.time() + _COOLDOWN_SECONDS
                self._failures[model_id] = 0
                print(f"[ModelHealth] {model_id} is in cooldown for {_COOLDOWN_SECONDS}s")

    def mark_unavailable(self, model_id: str):
        """A model that doesn't exist or isn't permitted won't recover soon."""
        with self._lock:
            self._failures.pop(model_id, None)
            self._cooldown[model_id] = time.time() + _UNAVAILABLE_SECONDS
            print(f"[ModelHealth] {model_id} is unavailable; skipping it for {_UNAVAILABLE_SECONDS}s")

    def record_success(self, model_id: str):
        with self._lock:
            self._failures.pop(model_id, None)
            self._cooldown.pop(model_id, None)


_health = _ModelHealth()

# ─── OpenAI-compatible client pointed at OpenRouter ──────────────────────────

# Retries are handled below per model, so the SDK's own retries are disabled
# and each request gets a bounded timeout (the SDK default is 10 minutes).
_REQUEST_TIMEOUT = 45

_client = OpenAI(
    api_key=OPENROUTER_API_KEY or "placeholder",
    base_url="https://openrouter.ai/api/v1",
    timeout=_REQUEST_TIMEOUT,
    max_retries=0,
)

# Many current free models reason before answering, and reasoning tokens count
# against max_tokens. Measured on nemotron-3-super: with reasoning at "low"
# effort the 1200-token synthesis budget was spent entirely on reasoning
# (finish_reason=length, empty content); disabled, the same request returned
# valid JSON in 459 tokens. The reasoning text is never used, so it's excluded
# when enabled. Models without reasoning support ignore this parameter.
_REASONING = (
    {"enabled": False}
    if OPENROUTER_REASONING in ("", "off", "false", "none")
    else {"effort": OPENROUTER_REASONING, "exclude": True}
)

# Upper bound when retrying an answer that was cut off before any content.
_MAX_TOKEN_CEILING = 4000

# ─── Retry helpers ────────────────────────────────────────────────────────────

_MAX_RETRIES = 2        # same-model retries for transient failures
_BACKOFF_BASE = 1.5     # seconds, exponential

# Categories worth retrying on the same model before moving on.
_RETRY_SAME_MODEL = {SERVER, CONNECTION}

# Model-specific categories, in order of how useful they are to report when
# every model failed (transient problems first: "try again" is actionable).
_MODEL_FAILURE_PRIORITY = [
    RATE_LIMIT, TIMEOUT, SERVER, EMPTY, MALFORMED,
    MODEL_NOT_FOUND, FORBIDDEN, BAD_REQUEST, UNKNOWN,
]


def _extract_text(response, model_id: str) -> str:
    """Return the completion text or raise a classified ProviderError."""
    choices = getattr(response, "choices", None)

    if not choices:
        # OpenRouter can return HTTP 200 with an error object from the upstream host.
        error = (getattr(response, "model_extra", None) or {}).get("error") or {}
        if error:
            status = error.get("code") if isinstance(error.get("code"), int) else None
            message = str(error.get("message", ""))
            raise ProviderError(category_for_status(status, message) if status else UNKNOWN,
                                f"{model_id}: upstream error {status}: {message[:200]}")
        raise ProviderError(MALFORMED, f"{model_id}: response had no choices")

    choice = choices[0]
    text = (choice.message.content or "").strip() if choice.message else ""

    if not text:
        reason = getattr(choice, "finish_reason", None)
        error = ProviderError(EMPTY, f"{model_id}: empty content (finish_reason={reason})")
        # Ran out of tokens before writing anything (usually spent on reasoning).
        error.truncated = reason == "length"
        raise error

    return text


# ─── Core generate function ───────────────────────────────────────────────────

def generate(
    prompt:      str,
    model_id:    str | None = None,
    max_tokens:  int | None = None,
    temperature: float | None = None,
) -> str:
    """
    Generate a response from OpenRouter.

    If model_id is supplied, tries only that model.
    Otherwise iterates through MODEL_REGISTRY in order, skipping models in
    cooldown (unless every model is cooling down), with per-model retry and
    backoff for transient failures.

    Raises AllModelsExhausted (with .category) if every model fails or an
    account-wide problem stops the attempt.
    Raises ModelUnavailable if a specific model_id was provided and it failed.
    """
    return generate_with_info(prompt, model_id, max_tokens, temperature)[0]


def _messages(prompt, images):
    """Chat messages for a prompt plus optional images [{"mime", "data"}]."""
    if not images:
        return [{"role": "user", "content": prompt}]
    content = [{"type": "text", "text": prompt}]
    for image in images:
        encoded = base64.b64encode(image["data"]).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:{image['mime']};base64,{encoded}"}})
    return [{"role": "user", "content": content}]


def _candidates(model_id, images=None):
    if model_id:
        return [model_id]
    all_ids = list(VISION_MODELS) if images else [m["id"] for m in MODEL_REGISTRY]
    healthy = [mid for mid in all_ids if _health.is_healthy(mid)]
    if not healthy:
        # Everything is cooling down: deprioritised, not banned. Try once more.
        print("[OpenRouter] Every model is in cooldown; trying them anyway")
        return all_ids
    return healthy


class _ModelState:
    """Retry bookkeeping for one model during one request."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.budget_raised = False


def _handle_failure(mid, attempt, exc, state, failures):
    """
    Apply the retry policy to one failed attempt. Shared by generate and
    stream so both follow the same rules.

    Returns "retry" (same model again) or "next" (move on); raises
    AllModelsExhausted for provider-wide failures.
    """
    category = classify_exception(exc)
    detail = log_detail(exc)
    print(f"[OpenRouter] {mid} attempt {attempt} failed [{category}]: {detail}")

    if (getattr(exc, "truncated", False) and not state.budget_raised
            and state.tokens < _MAX_TOKEN_CEILING):
        # Retry once with a bigger budget before giving up on this model.
        state.budget_raised = True
        state.tokens = min(state.tokens * 2, _MAX_TOKEN_CEILING)
        print(f"[OpenRouter] {mid} ran out of tokens; retrying with max_tokens={state.tokens}")
        return "retry"

    if category in _RETRY_SAME_MODEL and attempt <= _MAX_RETRIES:
        backoff = _BACKOFF_BASE ** attempt
        print(f"[OpenRouter] Retrying {mid} in {backoff:.1f}s")
        time.sleep(backoff)
        return "retry"

    if category in PROVIDER_WIDE:
        # Same account / same host for every model: don't cycle through them.
        print(f"[OpenRouter] Provider-wide failure [{category}]; not trying other models")
        raise AllModelsExhausted(category, f"{mid}: {detail[:300]}",
                                 retry_at=retry_at_from_exception(exc)) from exc

    if category in (MODEL_NOT_FOUND, FORBIDDEN):
        _health.mark_unavailable(mid)
    else:
        _health.record_failure(mid)

    failures.append(category)
    return "next"


def _exhausted(model_id, failures):
    summary = next(
        (c for c in _MODEL_FAILURE_PRIORITY if c in failures),
        UNKNOWN,
    )

    if model_id:
        return ModelUnavailable(summary, f"Model {model_id} failed: {failures}")

    return AllModelsExhausted(summary, f"All OpenRouter models failed: {failures}")


def generate_with_info(
    prompt:      str,
    model_id:    str | None = None,
    max_tokens:  int | None = None,
    temperature: float | None = None,
    images:      list | None = None,
):
    """
    Like generate(), but returns (text, info) where info records which model
    answered and how many API attempts it took (for response-time metrics).
    """
    if not OPENROUTER_API_KEY:
        raise AllModelsExhausted(NOT_CONFIGURED, "OPENROUTER_API_KEY is not set")

    tokens = max_tokens or MAX_TOKENS
    temp   = temperature if temperature is not None else TEMPERATURE

    failures: list[str] = []
    attempts_total = 0

    for mid in _candidates(model_id, images):

        state = _ModelState(tokens)

        for attempt in range(1, _MAX_RETRIES + 2):  # 1 try + _MAX_RETRIES retries

            attempts_total += 1

            try:
                print(f"[OpenRouter] Trying {mid} (attempt {attempt})")

                response = _client.chat.completions.create(
                    model=mid,
                    max_tokens=state.tokens,
                    temperature=temp,
                    messages=_messages(prompt, images),
                    extra_body={"reasoning": _REASONING},
                )

                text = _extract_text(response, mid)
                if getattr(response.choices[0], "finish_reason", None) == "length":
                    text += TRUNCATION_NOTE

                _health.record_success(mid)
                print(f"[OpenRouter] Success: {mid}")
                return text, {"model": mid, "attempts": attempts_total}

            except Exception as exc:
                if _handle_failure(mid, attempt, exc, state, failures) == "retry":
                    continue
                break

    raise _exhausted(model_id, failures)


# ─── Streaming ────────────────────────────────────────────────────────────────

def _stream_chunk_text(chunk, model_id):
    """Return (text, finish_reason) for one streamed chunk, raising on errors."""
    error = (getattr(chunk, "model_extra", None) or {}).get("error")
    if error:
        status = error.get("code") if isinstance(error.get("code"), int) else None
        message = str(error.get("message", ""))
        raise ProviderError(category_for_status(status, message) if status else UNKNOWN,
                            f"{model_id}: upstream stream error {status}: {message[:200]}")

    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return "", None
    choice = choices[0]
    delta = getattr(choice, "delta", None)
    return (getattr(delta, "content", None) or ""), getattr(choice, "finish_reason", None)


def stream(
    prompt:      str,
    max_tokens:  int | None = None,
    temperature: float | None = None,
    info:        dict | None = None,
    images:      list | None = None,
):
    """
    Stream a response as text chunks.

    Model fallback and retries follow the same policy as generate(), but only
    until the first token arrives: switching models mid-answer would splice two
    different answers together. A failure after streaming began raises a
    ProviderError with .partial = True.

    If `info` is given it is filled with the model used and attempt count.
    """
    if not OPENROUTER_API_KEY:
        raise AllModelsExhausted(NOT_CONFIGURED, "OPENROUTER_API_KEY is not set")

    info = info if info is not None else {}
    tokens = max_tokens or MAX_TOKENS
    temp   = temperature if temperature is not None else TEMPERATURE

    failures: list[str] = []
    info["attempts"] = 0

    for mid in _candidates(None, images):

        state = _ModelState(tokens)

        for attempt in range(1, _MAX_RETRIES + 2):

            info["attempts"] += 1
            started = False
            response = None

            try:
                print(f"[OpenRouter] Streaming {mid} (attempt {attempt})")

                response = _client.chat.completions.create(
                    model=mid,
                    max_tokens=state.tokens,
                    temperature=temp,
                    messages=_messages(prompt, images),
                    extra_body={"reasoning": _REASONING},
                    stream=True,
                )

                finish_reason = None

                for chunk in response:
                    text, reason = _stream_chunk_text(chunk, mid)
                    finish_reason = reason or finish_reason
                    if text:
                        if not started:
                            started = True
                            info["model"] = mid
                        yield text

                if not started:
                    error = ProviderError(EMPTY, f"{mid}: empty stream (finish_reason={finish_reason})")
                    error.truncated = finish_reason == "length"
                    raise error

                if finish_reason == "length":
                    yield TRUNCATION_NOTE

                _health.record_success(mid)
                print(f"[OpenRouter] Streamed: {mid}")
                return

            except Exception as exc:
                if started:
                    # Part of the answer is already on screen; don't splice in another model.
                    category = classify_exception(exc)
                    print(f"[OpenRouter] {mid} stream broke after start [{category}]: {log_detail(exc)}")
                    _health.record_failure(mid)
                    error = ProviderError(category, log_detail(exc))
                    error.partial = True
                    raise error from exc

                if _handle_failure(mid, attempt, exc, state, failures) == "retry":
                    continue
                break

            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()

    raise _exhausted(None, failures)
