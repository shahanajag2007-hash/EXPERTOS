"""
ProviderRouter: tries OpenRouter first, then Gemini, then Groq.
Ollama is last-resort (local, often unavailable in production).

Providers without credentials are skipped. Every failure is classified (see
services/errors.py) and logged with its category. Each provider is tried at
most once per request, in order.

Provider cooldown: when a provider fails in a way that will keep failing for a
while (a quota or account limit, a rejected key, a missing model, an
unreachable local server), it is skipped for a period instead of being called
again on every request. Quota cooldowns last until the reset time the provider
reported, when it reported one. Transient failures (rate limits, timeouts,
5xx, empty or malformed answers) never cool down the whole provider.

When every provider fails, an AIServiceError is raised with a user-safe
message built from all the providers' failures; raw provider errors stay in
the server log.

Every call is timed and stored in the ai_calls table (services/metrics.py)
with its request type, expert, the provider and model that answered, and the
full list of providers tried.
"""
import threading
import time
from datetime import datetime, timezone

from config import OPENROUTER_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, OLLAMA_URL
from providers import openrouter_provider, gemini_provider, groq_provider, ollama_provider
from services import metrics
from services.errors import (
    AIServiceError, ProviderError, classify_exception, log_detail, retry_at_from_exception,
    USER_MESSAGES, ACCOUNT_LIMIT, AUTH, CONNECTION, CREDITS, EMPTY, FORBIDDEN, MODEL_NOT_FOUND,
    NOT_CONFIGURED, TLS, UNKNOWN, UNSUPPORTED,
)

# How long to skip a provider after failures that won't clear quickly (seconds).
COOLDOWN_SECONDS = {
    ACCOUNT_LIMIT:   600,    # used only when the provider gave no reset time
    CREDITS:         1800,
    AUTH:            1800,
    FORBIDDEN:       1800,
    MODEL_NOT_FOUND: 1800,
    NOT_CONFIGURED:  1800,
    TLS:             600,
    CONNECTION:      120,
}
MAX_COOLDOWN_SECONDS = 24 * 3600


def _model_name(module):
    return getattr(module, "MODEL", None)


def _format_utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d %b %H:%M UTC")


class ProviderRouter:

    def __init__(self):
        self.providers = [
            {
                "name":    "OpenRouter",
                "generate": openrouter_provider.generate,
                "generate_with_info": openrouter_provider.generate_with_info,
                "stream":  openrouter_provider.stream,
                "vision":  True,
                "enabled": bool(OPENROUTER_API_KEY),
            },
            {
                "name":    "Gemini",
                "generate": gemini_provider.generate,
                "model":   "gemini-2.5-flash",
                "vision":  True,
                "enabled": bool(GEMINI_API_KEY),
            },
            {
                "name":    "Groq",
                "generate": groq_provider.generate,
                "model":   _model_name(groq_provider),
                "enabled": bool(GROQ_API_KEY),
            },
            {
                "name":    "Ollama",
                "generate": ollama_provider.generate,
                "model":   _model_name(ollama_provider),
                "enabled": bool(OLLAMA_URL),
            },
        ]
        self._lock = threading.Lock()
        self._cooldowns = {}   # provider name -> (until, category, retry_at)

    def enabled_provider_names(self):
        return [p["name"] for p in self.providers if p["enabled"]]

    # ── Cooldown ──────────────────────────────────────────────────────────────

    def _cooling(self, name, now=None):
        now = time.time() if now is None else now
        with self._lock:
            entry = self._cooldowns.get(name)
            if entry and entry[0] > now:
                return entry
            self._cooldowns.pop(name, None)
            return None

    def _start_cooldown(self, name, category, retry_at):
        seconds = COOLDOWN_SECONDS.get(category)
        if seconds is None:
            return
        now = time.time()
        until = retry_at if (category == ACCOUNT_LIMIT and retry_at) else now + seconds
        until = min(until, now + MAX_COOLDOWN_SECONDS)
        with self._lock:
            self._cooldowns[name] = (until, category, retry_at if category == ACCOUNT_LIMIT else None)
        print(f"[ProviderRouter] Skipping {name} until {_format_utc(until)} [{category}]")

    def _clear_cooldown(self, name):
        with self._lock:
            self._cooldowns.pop(name, None)

    def reset_cooldowns(self):
        with self._lock:
            self._cooldowns.clear()

    # ── Calls ─────────────────────────────────────────────────────────────────

    def _call(self, provider, prompt, max_tokens, temperature, images=None):
        """Run one provider; returns (text, info)."""
        extra = {"images": images} if images else {}
        if "generate_with_info" in provider:
            return provider["generate_with_info"](prompt, max_tokens=max_tokens, temperature=temperature, **extra)
        text = provider["generate"](prompt, max_tokens=max_tokens, temperature=temperature, **extra)
        return text, {"model": provider.get("model"), "attempts": 1}

    @staticmethod
    def _skip_if_no_vision(provider, images, failures, log):
        """Text-only providers can't take images; skipping them isn't a provider failure."""
        if not images or provider.get("vision"):
            return False
        failures.append({"provider": provider["name"], "category": UNSUPPORTED, "retry_at": None,
                         "skipped": True})
        log.append({"provider": provider["name"], "category": UNSUPPORTED, "skipped": True})
        return True

    def _record_failure(self, provider, exc, started, failures, log, info=None):
        category = classify_exception(exc)
        retry_at = retry_at_from_exception(exc)
        print(f"{provider['name']} failed [{category}]: {log_detail(exc)}")
        failures.append({"provider": provider["name"], "category": category, "retry_at": retry_at})
        log.append({
            "provider": provider["name"],
            "model": (info or {}).get("model") or provider.get("model"),
            "category": category,
            "ms": int((time.perf_counter() - started) * 1000),
        })
        self._start_cooldown(provider["name"], category, retry_at)
        return category

    def _skip_if_cooling(self, provider, failures, log):
        cooling = self._cooling(provider["name"])
        if not cooling:
            return False
        until, category, retry_at = cooling
        print(f"Skipping {provider['name']} until {_format_utc(until)} [{category}]")
        failures.append({"provider": provider["name"], "category": category,
                         "retry_at": retry_at or until, "skipped": True})
        log.append({"provider": provider["name"], "category": category, "skipped": True})
        return True

    def _all_failed(self, failures):
        if not failures:
            raise AIServiceError(USER_MESSAGES[NOT_CONFIGURED], NOT_CONFIGURED)

        print(f"[ProviderRouter] All providers failed: {[(f['provider'], f['category']) for f in failures]}")

        # Report the real failures; providers skipped for not reading images
        # matter only when nothing else was tried.
        real = [f for f in failures if f["category"] != UNSUPPORTED]
        if not real:
            raise AIServiceError(USER_MESSAGES[UNSUPPORTED], UNSUPPORTED,
                                 attempts=[{"provider": f["provider"], "category": UNSUPPORTED, "skipped": True}
                                           for f in failures])
        failures = real

        primary = failures[0]
        categories = [f["category"] for f in failures]
        known_resets = [f["retry_at"] for f in failures if f.get("retry_at")]
        retry_at = min(known_resets) if known_resets else None
        backups_failed = len(failures) > 1

        if all(c == ACCOUNT_LIMIT for c in categories):
            message = (
                "All of ExpertOS's AI providers have reached their usage limits."
                if backups_failed else
                "The AI provider's usage limit for this account has been reached."
            )
            if retry_at:
                message += f" The earliest expected reset is {_format_utc(retry_at)}."
            message += " Please try again later."
        elif primary["category"] == ACCOUNT_LIMIT:
            message = (
                "The primary AI provider's usage limit has been reached, and the backup "
                "providers couldn't complete the request either."
            )
            if primary.get("retry_at"):
                message += f" The primary provider's limit resets {_format_utc(primary['retry_at'])}."
            message += " Please try again later."
        else:
            message = USER_MESSAGES.get(primary["category"], USER_MESSAGES[UNKNOWN])
            if backups_failed:
                message += " The backup AI providers couldn't complete the request either."

        attempts = [
            {"provider": f["provider"], "category": f["category"], "skipped": bool(f.get("skipped"))}
            for f in failures
        ]
        raise AIServiceError(message, primary["category"], attempts=attempts, retry_at=retry_at)

    def generate(
        self,
        prompt:       str,
        max_tokens:   int | None = None,
        temperature:  float | None = None,
        request_type: str = "other",
        expert_key:   str | None = None,
        images:       list | None = None,
    ) -> str:

        failures = []   # per provider: {"provider", "category", "retry_at", "skipped"?}
        log = []        # metrics: every provider tried, in order
        timer = metrics.Timer()
        attempts = 0

        for provider in self.providers:

            if not provider["enabled"]:
                continue

            if self._skip_if_no_vision(provider, images, failures, log):
                continue

            if self._skip_if_cooling(provider, failures, log):
                continue

            started = time.perf_counter()
            info = {}

            try:
                print(f"\n========== TRYING {provider['name']} ==========")

                response, info = self._call(provider, prompt, max_tokens, temperature, images)
                attempts += info.get("attempts", 1)

                response = (response or "").strip()

                if response == "":
                    raise ProviderError(EMPTY, "Provider returned a blank response.")

                print(f"{provider['name']} succeeded.\n")
                self._clear_cooldown(provider["name"])
                log.append({"provider": provider["name"], "model": info.get("model"), "category": None,
                            "ms": int((time.perf_counter() - started) * 1000)})
                metrics.record_ai_call(request_type, timer, True, provider["name"], info.get("model"),
                                       attempts, expert_key=expert_key, provider_attempts=log)
                return response

            except Exception as exc:
                attempts += 1
                self._record_failure(provider, exc, started, failures, log, info)
                continue

        metrics.record_ai_call(request_type, timer, False, attempts=max(attempts, 1),
                               error_category=failures[0]["category"] if failures else NOT_CONFIGURED,
                               expert_key=expert_key, provider_attempts=log)
        self._all_failed(failures)

    def stream(
        self,
        prompt:       str,
        max_tokens:   int | None = None,
        temperature:  float | None = None,
        request_type: str = "other",
        expert_key:   str | None = None,
        timer:        "metrics.Timer | None" = None,
        images:       list | None = None,
    ):
        """
        Yield the response as text chunks. Providers that can't stream return
        their whole answer as one chunk. Falls back to the next provider only
        if nothing has been sent yet. `timer`, if given, gets its first-token
        time marked so the caller's operation measurement includes it.
        """
        failures = []
        log = []
        call_timer = metrics.Timer()
        attempts = 0

        for provider in self.providers:

            if not provider["enabled"]:
                continue

            if self._skip_if_no_vision(provider, images, failures, log):
                continue

            if self._skip_if_cooling(provider, failures, log):
                continue

            info = {}
            sent_any = False
            started = time.perf_counter()

            try:
                print(f"\n========== STREAMING {provider['name']} ==========")

                if "stream" in provider:
                    chunks = provider["stream"](prompt, max_tokens=max_tokens, temperature=temperature,
                                                info=info, **({"images": images} if images else {}))
                else:
                    text, info = self._call(provider, prompt, max_tokens, temperature, images)
                    chunks = [text] if (text or "").strip() else []

                for chunk in chunks:
                    if not chunk:
                        continue
                    if not sent_any:
                        sent_any = True
                        call_timer.mark_first_token()
                        if timer is not None:
                            timer.mark_first_token()
                    yield chunk

                attempts += info.get("attempts", 1)

                if not sent_any:
                    raise ProviderError(EMPTY, "Provider returned a blank response.")

                self._clear_cooldown(provider["name"])
                log.append({"provider": provider["name"], "model": info.get("model"), "category": None,
                            "ms": int((time.perf_counter() - started) * 1000)})
                metrics.record_ai_call(request_type, call_timer, True, provider["name"], info.get("model"),
                                       attempts, expert_key=expert_key, streamed="stream" in provider,
                                       provider_attempts=log)
                return

            except Exception as exc:
                attempts += info.get("attempts", 1)
                category = self._record_failure(provider, exc, started, failures, log, info)

                if sent_any:
                    metrics.record_ai_call(request_type, call_timer, False, provider["name"],
                                           info.get("model"), attempts, error_category=category,
                                           expert_key=expert_key, streamed=True, provider_attempts=log)
                    error = AIServiceError(
                        "The response was interrupted. " + USER_MESSAGES.get(category, USER_MESSAGES[UNKNOWN]),
                        category,
                    )
                    error.partial = True
                    raise error from exc

                continue

        metrics.record_ai_call(request_type, call_timer, False, attempts=max(attempts, 1),
                               error_category=failures[0]["category"] if failures else NOT_CONFIGURED,
                               expert_key=expert_key, streamed=True, provider_attempts=log)
        self._all_failed(failures)


provider_router = ProviderRouter()


def generate(
    prompt:       str,
    max_tokens:   int | None = None,
    temperature:  float | None = None,
    request_type: str = "other",
    expert_key:   str | None = None,
    images:       list | None = None,
) -> str:
    return provider_router.generate(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        request_type=request_type,
        expert_key=expert_key,
        **({"images": images} if images else {}),
    )


def stream(prompt, max_tokens=None, temperature=None, request_type="other", expert_key=None, timer=None,
           images=None):
    return provider_router.stream(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        request_type=request_type,
        expert_key=expert_key,
        timer=timer,
        **({"images": images} if images else {}),
    )
