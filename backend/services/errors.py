"""
Errors that are safe to show to the user, and classification of AI provider
failures.

Routes translate AIServiceError / AIResponseError into JSON error responses;
anything else is treated as an unexpected server error and its details stay in
the server log.
"""
import ssl


class AIServiceError(Exception):
    """No AI provider could produce a response."""

    status_code = 503

    def __init__(self, message, category="unknown", attempts=None, retry_at=None):
        super().__init__(message)
        self.category = category
        # [{"provider", "category", "skipped"}]; names and categories only.
        self.attempts = attempts or []
        # Unix time when a provider is expected to accept requests again, if known.
        self.retry_at = retry_at


class AIResponseError(Exception):
    """The AI produced a response, but it could not be parsed."""

    status_code = 502
    category = "malformed_response"


# ─── Provider failure categories ─────────────────────────────────────────────

TLS              = "tls"                 # certificate verification failed
CONNECTION       = "connection"          # DNS / refused / network unreachable
TIMEOUT          = "timeout"
AUTH             = "auth"                # 401, invalid API key
CREDITS          = "credits"             # 402, insufficient credits
FORBIDDEN        = "forbidden"           # 403, model/region/feature restricted
ACCOUNT_LIMIT    = "account_rate_limit"  # 429 shared by every model on the account
RATE_LIMIT       = "rate_limit"          # 429 for one model / upstream host
MODEL_NOT_FOUND  = "model_not_found"     # 404, unknown or retired model ID
BAD_REQUEST      = "bad_request"         # 400
SERVER           = "server"              # 5xx
EMPTY            = "empty_response"
MALFORMED        = "malformed_response"
NOT_CONFIGURED   = "not_configured"
UNSUPPORTED      = "unsupported_input"   # e.g. images sent to a text-only provider
UNKNOWN          = "unknown"

# Failures that affect every model behind the same provider account or host,
# so trying the provider's other models is pointless.
PROVIDER_WIDE = {TLS, CONNECTION, AUTH, CREDITS, ACCOUNT_LIMIT, NOT_CONFIGURED}

# Messages shown to users. They describe what happened without exposing keys,
# hosts, payloads or stack traces.
USER_MESSAGES = {
    TLS: (
        "ExpertOS couldn't establish a secure connection to the AI provider "
        "(certificate verification failed). The server's certificate setup needs attention."
    ),
    CONNECTION: "ExpertOS couldn't reach the AI provider. Please check the server's internet connection and try again.",
    TIMEOUT: "The AI experts took too long to respond. Please try again.",
    AUTH: "The AI provider rejected the server's API key. The ExpertOS administrator needs to update it.",
    CREDITS: "The AI provider account has run out of credits. The ExpertOS administrator needs to add credits.",
    FORBIDDEN: "The configured AI models aren't available to this account.",
    ACCOUNT_LIMIT: "The AI provider's usage limit for this account has been reached. Please try again later.",
    RATE_LIMIT: "The AI models are busy right now. Please try again in a minute.",
    MODEL_NOT_FOUND: "None of the configured AI models are currently available. The model list needs updating.",
    BAD_REQUEST: "The AI provider couldn't process this request. Please try rephrasing it.",
    SERVER: "The AI provider is having problems right now. Please try again shortly.",
    EMPTY: "The AI returned an empty response. Please try again.",
    MALFORMED: "The AI returned a response ExpertOS couldn't read. Please try again.",
    NOT_CONFIGURED: "No AI provider is configured. Add an API key to backend/.env and restart the backend.",
    UNSUPPORTED: (
        "None of the available AI models can read images right now. Remove the image or "
        "describe it in your message, and try again."
    ),
    UNKNOWN: "The AI consultation service is temporarily unavailable. Please try again in a minute.",
}

# Phrases that mark a 429 as an account-wide limit rather than one busy model.
_ACCOUNT_LIMIT_PHRASES = (
    "free-models-per-day", "free-models-per-min", "quota", "credits",
)


class ProviderError(Exception):
    """A classified provider failure. `detail` is for server logs only."""

    def __init__(self, category, detail="", retry_at=None):
        super().__init__(detail or category)
        self.category = category
        self.detail = detail
        self.retry_at = retry_at


_MAX_RETRY_SECONDS = 2 * 24 * 3600


def retry_at_from_exception(exc, now=None):
    """
    When the provider says it will accept requests again, as Unix time, or None.

    Reads only rate-limit metadata:
      - OpenRouter: `x-ratelimit-reset` header (epoch milliseconds);
      - standard `Retry-After` header (seconds);
      - Google APIs: RetryInfo.retryDelay in the error details (e.g. "68982s").
    """
    import time as _time

    now = _time.time() if now is None else now

    for e in _exception_chain(exc):
        explicit = getattr(e, "retry_at", None)
        if isinstance(explicit, (int, float)):
            return explicit

        headers = getattr(getattr(e, "response", None), "headers", None)
        if headers is not None:
            reset = headers.get("x-ratelimit-reset")
            if reset and str(reset).isdigit():
                value = int(reset)
                value = value / 1000 if value > 10**12 else value   # ms or s epoch
                if now < value < now + _MAX_RETRY_SECONDS:
                    return value
            after = headers.get("retry-after")
            if after and str(after).isdigit() and int(after) < _MAX_RETRY_SECONDS:
                return now + int(after)

        for detail in getattr(e, "details", None) or []:
            if isinstance(detail, dict) and str(detail.get("@type", "")).endswith("RetryInfo"):
                delay = str(detail.get("retryDelay", "")).rstrip("s")
                try:
                    seconds = float(delay)
                except ValueError:
                    continue
                if 0 < seconds < _MAX_RETRY_SECONDS:
                    return now + seconds

    return None


def _exception_chain(exc):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _status_code(exc):
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(exc, "code", None),
    ):
        if isinstance(candidate, int) and 100 <= candidate <= 599:
            return candidate
    return None


def category_for_status(status, message=""):
    message = message.lower()

    if status == 401:
        return AUTH
    if status == 402:
        return CREDITS
    if status == 403:
        return FORBIDDEN
    if status == 404:
        return MODEL_NOT_FOUND
    if status == 408:
        return TIMEOUT
    if status == 429:
        if any(p in message for p in _ACCOUNT_LIMIT_PHRASES):
            return ACCOUNT_LIMIT
        return RATE_LIMIT
    if status == 400:
        # Gemini reports an invalid key as 400.
        if "api key not valid" in message or "api_key_invalid" in message:
            return AUTH
        # OpenRouter reports unknown/retired model IDs as 400.
        if "not a valid model id" in message:
            return MODEL_NOT_FOUND
        return BAD_REQUEST
    if status is not None and status >= 500:
        return SERVER
    return UNKNOWN


def log_detail(exc):
    """
    A short description of a provider error for server logs: the status and
    the provider's error message only, never the raw response body (which can
    include account identifiers).
    """
    if isinstance(exc, ProviderError):
        return exc.detail or exc.category

    status = _status_code(exc)
    body = getattr(exc, "body", None)
    if status is not None and isinstance(body, dict):
        error = body.get("error", body)
        message = error.get("message") if isinstance(error, dict) else str(error)
        return f"HTTP {status}: {str(message)[:200]}"

    return f"{type(exc).__name__}: {str(exc)[:200]}"


def classify_exception(exc):
    """Map an exception from any provider SDK to a failure category."""
    # Already-classified errors (ProviderError, AIServiceError, AIResponseError)
    # keep their category. Note AIServiceError.status_code is the HTTP status
    # ExpertOS responds with, not an upstream status, so it must not be read below.
    category = getattr(exc, "category", None)
    if isinstance(category, str):
        return category

    chain = list(_exception_chain(exc))

    # TLS problems surface wrapped in connection errors, so check them first.
    for e in chain:
        if isinstance(e, ssl.SSLCertVerificationError) or "certificate_verify_failed" in str(e).lower():
            return TLS

    for e in chain:
        status = _status_code(e)
        if status is not None:
            return category_for_status(status, str(e))

    for e in chain:
        name = type(e).__name__.lower()
        if isinstance(e, TimeoutError) or "timeout" in name:
            return TIMEOUT

    for e in chain:
        name = type(e).__name__.lower()
        if isinstance(e, ConnectionError) or "connect" in name:
            return CONNECTION

    return UNKNOWN
