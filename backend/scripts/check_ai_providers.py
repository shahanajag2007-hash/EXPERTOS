"""
Diagnose the OpenRouter integration step by step without printing secrets.

    cd backend
    python scripts/check_ai_providers.py          # TLS, auth, model catalogue
    python scripts/check_ai_providers.py --live   # also one tiny completion
                                                  # through the real backend router

--live sends one short request (counts toward free-tier daily limits).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

import config  # noqa: E402  (applies truststore before any request)
from services.openrouter_client import MODEL_REGISTRY  # noqa: E402

BASE = "https://openrouter.ai/api/v1"


def step(name, ok, info=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + info if info else ''}")
    return ok


def main():
    print(f"System certificate store: {'on' if config.USE_SYSTEM_CERTIFICATES else 'off'}")

    # 1. TLS / connectivity (public endpoint, no credentials)
    try:
        res = httpx.get(f"{BASE}/models", timeout=20)
        catalogue = {m["id"] for m in res.json()["data"]}
        step("HTTPS connection to openrouter.ai", True, f"{len(catalogue)} models listed")
    except Exception as exc:
        step("HTTPS connection to openrouter.ai", False, f"{type(exc).__name__}: {str(exc)[:200]}")
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            print("       Certificate not trusted. Install truststore (pip install -r requirements.txt)")
            print("       and keep USE_SYSTEM_CERTIFICATES=true.")
        return 1

    # 2. Credentials
    if not config.OPENROUTER_API_KEY:
        step("OPENROUTER_API_KEY configured", False, "add it to backend/.env (see .env.example)")
        return 1
    step("OPENROUTER_API_KEY configured", True, "value not shown")

    res = httpx.get(f"{BASE}/key", headers={"Authorization": f"Bearer {config.OPENROUTER_API_KEY}"}, timeout=20)
    if not step("API key accepted by OpenRouter", res.status_code == 200, f"HTTP {res.status_code}"):
        return 1
    data = res.json().get("data", {})
    print(f"       free tier: {data.get('is_free_tier')}, usage: {data.get('usage')}, "
          f"limit remaining: {data.get('limit_remaining')}")

    # 3. Configured models exist
    missing = [m["id"] for m in MODEL_REGISTRY if m["id"] not in catalogue]
    for m in MODEL_REGISTRY:
        step(f"model listed: {m['id']}", m["id"] not in missing)
    if len(missing) == len(MODEL_REGISTRY):
        print("       None of the configured models exist. Set OPENROUTER_MODELS in backend/.env.")
        return 1

    # 4. Optional real completion through the backend's own router
    if "--live" in sys.argv:
        from services.openrouter_client import generate
        from services.errors import ProviderError
        try:
            text = generate("Reply with only the word SUCCESS.", max_tokens=300)
            step("live completion via ExpertOS model router", bool(text), repr(text[:60]))
        except ProviderError as exc:
            step("live completion via ExpertOS model router", False, f"category={exc.category}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
