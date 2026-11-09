"""
model_router.py — Legacy compatibility module.

The intelligent model routing now lives inside openrouter_client.py
(MODEL_REGISTRY, _ModelHealth, retry logic).

This module is preserved so any existing import of
`from services.model_router import generate_response`
continues to work.
"""
from services.openrouter_client import generate as _generate


def generate_response(prompt: str) -> str:
    """Convenience wrapper used by legacy callers."""
    return _generate(prompt)