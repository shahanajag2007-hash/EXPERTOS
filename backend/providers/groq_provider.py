from groq import Groq

from config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    MAX_TOKENS,
    TEMPERATURE,
)
from services.errors import ProviderError, EMPTY, MALFORMED

# Verified against Groq's /openai/v1/models list for this account on
# 2026-10-19 (the previous llama-3.3-70b-versatile was no longer listed).
# Override with GROQ_MODEL in backend/.env.
MODEL = GROQ_MODEL

# gpt-oss models reason before answering and those tokens count against
# max_tokens (118 completion tokens for a one-sentence reply when verified),
# so the cap gets headroom. It's a ceiling: short answers don't take longer.
REASONING_HEADROOM = 1024

# Created lazily: Groq() raises when no API key is set, which would otherwise
# stop the whole backend from starting.
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY, timeout=60)
    return _client


def generate(
    prompt,
    max_tokens=None,
    temperature=None
):

    try:

        response = _get_client().chat.completions.create(

            model=MODEL,

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            max_tokens=(
                max_tokens
                if max_tokens is not None
                else MAX_TOKENS
            ) + REASONING_HEADROOM,

            temperature=(
                temperature
                if temperature is not None
                else TEMPERATURE
            )

        )

        if (
            response is None
            or
            not response.choices
        ):

            raise ProviderError(MALFORMED, "Groq returned no choices.")

        choice = response.choices[0]
        text = (choice.message.content or "").strip()

        if text == "":

            raise ProviderError(EMPTY, f"Groq returned a blank response (finish_reason={choice.finish_reason}).")

        # Never pass on an answer that was cut off mid-sentence.
        if choice.finish_reason == "length":

            raise ProviderError(EMPTY, "Groq response was truncated (finish_reason=length).")

        return text

    except ProviderError:
        raise

    except Exception as e:

        raise Exception(
            f"Groq Provider Error: {e}"
        )
