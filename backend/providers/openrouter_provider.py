"""
OpenRouter provider — thin wrapper so ProviderRouter can call it uniformly.
"""
from services.openrouter_client import (
    generate_with_info as _generate_with_info,
    stream as _stream,
)


def generate(
    prompt:      str,
    max_tokens:  int | None = None,
    temperature: float | None = None,
) -> str:
    """
    Delegate to the OpenRouter client, which handles model selection,
    retries, health tracking and fallback automatically.

    Failures are raised as classified ProviderErrors (AllModelsExhausted /
    ModelUnavailable) so ProviderRouter can report the real cause and fall
    through to the next provider.
    """
    return generate_with_info(prompt, max_tokens, temperature)[0]


def generate_with_info(prompt, max_tokens=None, temperature=None, images=None):
    """(text, {"model", "attempts"})"""
    return _generate_with_info(prompt, max_tokens=max_tokens, temperature=temperature, images=images)


def stream(prompt, max_tokens=None, temperature=None, info=None, images=None):
    """Yield text chunks as they arrive."""
    return _stream(prompt, max_tokens=max_tokens, temperature=temperature, info=info, images=images)
