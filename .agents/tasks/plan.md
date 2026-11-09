# Implementation Plan — ExpertOS P1/P2/P3 Engineering Improvements

**Source:** Technical Audit findings, approved by owner.  
**Objective:** Improve security, reliability, and code quality without changing any user-visible behaviour.

**Critical constraints (every stage must honour these):**
- Do NOT change any UI component or frontend code (except Stage 7's `.env.example`)
- Do NOT change expert identities, personalities, system prompts, or room navigation
- Do NOT change role-switching behaviour or provider fallback order (OpenRouter → Gemini → Groq → Ollama)
- Do NOT implement items the audit marked "requires approval"
- After each stage: run the full test suite; stop if any test regresses

---

## STAGE 1 — Security: Panel Authentication (P1-1)

**What to do:**  
Add `owner = auth.require_owner(_owner())` at the very start of `_panel_request()`, before the body is read. This is the identical call pattern used in `/analyze` (line ~195) and `/expert/recommend` (line ~325). Store the result in a local variable named `owner` (even if not used further). This enforces that the browser must supply a valid `X-Client-Id` header (or a session Bearer token) — exactly what the frontend already sends on every request — without requiring a user account.

**Why this pattern and not a decorator:**  
`_panel_request()` is a shared helper called from both `panel()` and `panel_stream()`. Adding the check there covers both routes in one place, consistent with how `/analyze` factored it.

**Exact change in `backend/app.py`:**  
Locate the `_panel_request()` function (currently starts with `data = _json_body()`). Insert the following as the first two lines of the function body:

```python
    owner = auth.require_owner(_owner())   # P1-1: panel requires a client identity
```

The variable `owner` satisfies lint; it is intentionally unused beyond the auth check for now.

**Test additions in `backend/tests/test_api.py`:**  
Add a new `PanelAuthTests` class. Required test methods:
1. `test_panel_requires_client_id_returns_401` — POST `/panel` with no `X-Client-Id` header; assert `status_code == 401` and `body["code"] == "unauthorized"`. Use `_testenv.client(app, client_id=None)` to strip the header.
2. `test_panel_succeeds_with_valid_client_id` — POST `/panel` with a valid `X-Client-Id` (the default test client); mock `app.run_panel` to return a minimal valid result dict; assert `status_code == 200`.
3. `test_panel_stream_requires_client_id_returns_401` — Same as test 1 but against `/panel/stream`.
4. `test_panel_stream_succeeds_with_valid_client_id` — POST `/panel/stream` with valid `X-Client-Id`; mock `app.iter_panel` to yield `("done", {...minimal...})`; assert response is 200.

**Files to modify:** `backend/app.py`, `backend/tests/test_api.py`  
**Verify:** `python -m pytest backend/tests/test_api.py -v --tb=short` from `c:\Users\shaha\OneDrive\Desktop\ExpertOS-kiro\backend` — all pre-existing tests pass, new `PanelAuthTests` tests pass.

---

## STAGE 2 — Security: Knowledge Rate Limiting (P1-2)

**What to do:**  
Add `_ai_rate_limited()` to the `/knowledge` route handler. Place it after the input validation block (after the `if not technology:` guard) and before the `metrics.track_operation(...)` call. Use the exact same idiom as `/chat` and `/panel`:

```python
    limited = _ai_rate_limited()
    if limited:
        return limited
```

Do NOT add `auth.require_owner` to this endpoint (the audit rates this as "optional" and the user's instruction is only to add the rate limiter). Do NOT change what `/knowledge` returns on success.

**Test addition in `backend/tests/test_api.py`:**  
Add `test_knowledge_is_rate_limited` to a new `KnowledgeTests` class. The test should mock the `ai_limiter.allow` method to return `False` (simulating a full bucket), POST to `/knowledge`, and assert `status_code == 429`.

**Files to modify:** `backend/app.py`, `backend/tests/test_api.py`  
**Verify:** `python -m pytest backend/tests/test_api.py -v --tb=short` — all tests pass including new `KnowledgeTests`.

---

## STAGE 3 — AI Reliability: Fix Ollama Provider (P1-3)

**What to do:**  
Replace the outer `except Exception as e: raise Exception(f"Ollama Provider Error: {e}")` wrapper in `backend/providers/ollama_provider.py` with targeted handlers that raise `ProviderError` with the correct category, matching the `groq_provider.py` pattern exactly.

**Exact replacement of the exception handler block:**

The current code wraps everything in a single `try/except Exception`. Replace it with:

```python
    except ProviderError:
        raise

    except requests.exceptions.Timeout:
        raise ProviderError(TIMEOUT, "Ollama request timed out after 120s.")

    except requests.exceptions.ConnectionError as e:
        raise ProviderError(CONNECTION, f"Ollama unreachable: {e}")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status is not None and status >= 500:
            raise ProviderError(SERVER, f"Ollama HTTP {status}")
        raise ProviderError(UNKNOWN, f"Ollama HTTP error: {e}")

    except Exception as e:
        raise ProviderError(UNKNOWN, f"Ollama unexpected error: {e}")
```

Also add the import at the top of `ollama_provider.py`:

```python
from services.errors import ProviderError, TIMEOUT, CONNECTION, SERVER, UNKNOWN
```

Note: `requests.exceptions.Timeout` is a subclass of `requests.exceptions.ConnectionError` in some versions of `requests`, so `Timeout` must be caught **before** `ConnectionError` — which the ordering above already ensures.

The `text is None` and `text == ""` checks inside the `try` block should be updated to raise `ProviderError(EMPTY, "...")` instead of `Exception(...)`. Add `EMPTY` to the import.

**Test additions in `backend/tests/test_provider_fallback.py`:**  
Add an `OllamaTests` class inheriting from `FallbackBase`. Enable only Ollama in `setUp`:

```python
def setUp(self):
    super().setUp()
    for p in self.router.providers:
        p["enabled"] = p["name"] == "Ollama"
    # patch requests.post used by ollama_provider
    self.requests_post = mock.patch("providers.ollama_provider.requests.post").start()
    self.addCleanup(mock.patch.stopall)
```

Required test methods:
1. `test_ollama_connection_error_raises_provider_error_connection` — set `self.requests_post.side_effect = requests.exceptions.ConnectionError("refused")`; call `self.router.generate("q")` inside `assertRaises(AIServiceError)`; assert `err.attempts[-1]["category"] == CONNECTION`.
2. `test_ollama_timeout_raises_provider_error_timeout` — set side_effect to `requests.exceptions.Timeout()`; assert category is `TIMEOUT`.
3. `test_ollama_http_500_raises_provider_error_server` — configure mock to return a response that raises `HTTPError` with status 500 (use `mock.Mock(raise_for_status=mock.Mock(side_effect=requests.exceptions.HTTPError(response=mock.Mock(status_code=500))))`); assert category is `SERVER`.
4. `test_ollama_success` — configure mock to return `mock.Mock(raise_for_status=lambda: None, json=lambda: {"response": "hello"})` and assert `self.router.generate("q") == "hello"`.

**Files to modify:** `backend/providers/ollama_provider.py`, `backend/tests/test_provider_fallback.py`  
**Verify:** `python -m pytest backend/tests/test_provider_fallback.py -v --tb=short` — all pre-existing tests pass plus new `OllamaTests` pass.

---

## STAGE 4 — AI Reliability: Fix Gemini Exception Wrapping (P1-4)

**What to do:**  
In `backend/providers/gemini_provider.py`, the outer `except Exception as e: raise Exception(f"Gemini Provider Error: {e}")` clause converts typed Google SDK exceptions (like `ResourceExhausted`, `ServiceUnavailable`) into plain `Exception` objects, defeating `classify_exception()` in `errors.py`. Remove this outer wrapper.

**Exact change:**  
Find the final `except Exception as e:` block (after `except ProviderError: raise`):

```python
    except ProviderError:
        raise

    except Exception as e:

        raise Exception(
            f"Gemini Provider Error: {e}"
        )
```

Replace it with just:

```python
    except ProviderError:
        raise
```

This preserves the `ProviderError` re-raise and lets all other typed exceptions (`google.api_core.exceptions.ResourceExhausted`, `google.api_core.exceptions.ServiceUnavailable`, etc.) propagate unchanged to `classify_exception()` in the provider router. Do NOT change `THINKING_HEADROOM`, the 45-second timeout, the model name, `GenerationConfig`, or anything else in this file.

**Test additions in `backend/tests/test_provider_fallback.py`:**  
Add two test methods to the existing `GeminiFallbackTests` class:

1. `test_gemini_resource_exhausted_classifies_as_rate_limit` — set `self.gemini.side_effect = google_exceptions.ResourceExhausted("Quota exceeded")`; call `self.router.generate("q")` (OpenRouter already fails in setUp); assert `self.router._cooling("Gemini")[1] == RATE_LIMIT`.
2. `test_gemini_service_unavailable_classifies_as_server` — set `self.gemini.side_effect = google_exceptions.ServiceUnavailable("overloaded")`; call `self.router.generate("q")` and assert the final attempt's category is `SERVER`. (`ServiceUnavailable` is a 503 → `SERVER`; it should not trigger a provider-level cooldown since `SERVER` is transient — verify `self.router._cooling("Gemini")` is `None`.)

**Files to modify:** `backend/providers/gemini_provider.py`, `backend/tests/test_provider_fallback.py`  
**Verify:** `python -m pytest backend/tests/test_provider_fallback.py -v --tb=short` — all tests pass.

---

## STAGE 5 — Dependency Cleanup (P1-6)

**What to do:**  
Remove from `backend/requirements.txt` only the packages that are confirmed unused after reading every Python file. The import audit above is complete; below is the definitive list of what to remove and why:

| Package | Remove? | Reason |
|---|---|---|
| `fastapi` | ✅ Remove | No `import fastapi` anywhere |
| `uvicorn` | ✅ Remove | No `import uvicorn` anywhere |
| `starlette` | ✅ Remove | No direct import; was a FastAPI transitive dep |
| `openai-whisper` | ✅ Remove | No `import whisper` (the `whisper` package) anywhere in app code |
| `whisper` | ✅ Remove | Same — no usage |
| `torch` | ✅ Remove | Only pulled in by whisper/transformers; neither used |
| `transformers` | ✅ Remove | No `import transformers` anywhere |
| `tokenizers` | ✅ Remove | No direct import; transitive dep of transformers |
| `huggingface-hub` | ✅ Remove | No `import huggingface_hub` anywhere |
| `hf-xet` | ✅ Remove | Transitive dep of huggingface-hub |
| `google-cloud-dialogflow` | ✅ Remove | No `import google.cloud.dialogflow` anywhere |
| `google-genai` | ✅ Remove | No `import google.genai` anywhere; app uses `google-generativeai` (the `genai` alias) |
| `tiktoken` | ✅ Remove | No `import tiktoken` anywhere |
| `numba` | ✅ Remove | No `import numba` anywhere; dep of whisper |
| `llvmlite` | ✅ Remove | Transitive dep of numba |
| `SQLAlchemy` | ✅ Remove | App uses raw sqlite3; no `import sqlalchemy` |
| `PyMySQL` | ✅ Remove | No `import pymysql` anywhere |
| `greenlet` | ✅ Remove | No direct import; transitive dep of SQLAlchemy |
| `safetensors` | ✅ Remove | No `import safetensors` anywhere |
| `semantic-version` | ✅ Remove | No `import semantic_version` anywhere |
| `setuptools-rust` | ✅ Remove | No direct import; build dep for tokenizers |
| `tqdm` | ✅ Remove | No `import tqdm` anywhere in any `.py` file (grep confirmed: zero matches) |

**Packages to KEEP (confirmed used or required):**
- `Flask`, `flask-cors`, `Werkzeug` — core web framework
- `python-dotenv` — `from dotenv import load_dotenv` in `config.py`
- `openai` — `from openai import OpenAI` in `openrouter_client.py` and `test_openrouter.py`
- `groq` — `from groq import Groq` in `groq_provider.py`
- `google-generativeai` — `import google.generativeai as genai` in `gemini_provider.py`
- `requests` — `import requests` in `ollama_provider.py` and `check_ai_providers.py` (via httpx too)
- `httpx` — `import httpx` in `openrouter_client.py`, `check_ai_providers.py`, and tests
- `grpcio`, `grpcio-status` — required by `google-generativeai` at runtime even though not directly imported
- `google-api-core`, `google-auth`, `googleapis-common-protos`, `proto-plus`, `protobuf`, `pyasn1`, `pyasn1_modules`, `rsa` — all transitive runtime dependencies of `google-generativeai`
- `cachetools` — transitive dep of `google-auth`
- `truststore` — `import truststore` in `config.py` (conditional)
- `pypdf` — `from pypdf import PdfReader` in `services/files.py`
- `numpy` — Keep: `torch` and `whisper` pulled it in, but check if `google-generativeai` or `openai` requires it at runtime. Since both SDKs use it internally, keep it.
- `networkx`, `sympy`, `mpmath` — these are torch/transformers transitive deps. After removing torch and transformers, they are no longer needed. Remove all three.
- `packaging` — used by several remaining SDKs as a runtime dep; keep.
- `pydantic`, `pydantic_core` — used by `openai` SDK; keep.
- `annotated-types`, `typing_extensions`, `typing-inspection` — used by pydantic; keep.
- `anyio`, `sniffio`, `h11`, `httpcore` — used by httpx; keep.
- `blinker` — used by Flask signalling; keep.
- `certifi` — truststore uses it as fallback; keep.
- `cffi`, `cryptography`, `pycparser` — used by some SDK TLS code; keep.
- `colorama` — used by click (Flask dep) on Windows; keep.
- `click` — Flask dependency; keep.
- `distro`, `jiter` — used by openai SDK; keep.
- `filelock` — transitive dep of huggingface-hub. After removing huggingface-hub, no longer needed. Remove.
- `fsspec` — transitive dep of huggingface-hub/torch. After removing both, no longer needed. Remove.
- `idna` — used by httpx/requests; keep.
- `itsdangerous` — Flask session signing; keep.
- `Jinja2`, `MarkupSafe` — Flask templating; keep.
- `more-itertools` — no direct import found; transitive dep of removed packages. Remove.
- `regex` — no direct import; was a dep of tiktoken/tokenizers. Remove.
- `setuptools` — keep (pip build tooling).
- `six` — used by some google auth libs; keep.
- `tenacity` — used by `google-api-core` for retries; keep.
- `urllib3` — used by requests; keep.
- `websockets` — used by some SDKs; keep (openai SDK uses it for streaming).
- `PyYAML` — no direct import but used by openrouter/google SDKs. Keep.

**Summary of removals:**
Remove these 23 lines from `requirements.txt`:
`fastapi`, `uvicorn`, `starlette`, `openai-whisper`, `whisper`, `torch`, `transformers`, `tokenizers`, `huggingface-hub`, `hf-xet`, `google-cloud-dialogflow`, `google-genai`, `tiktoken`, `numba`, `llvmlite`, `SQLAlchemy`, `PyMySQL`, `greenlet`, `safetensors`, `semantic-version`, `setuptools-rust`, `tqdm`, and additionally `networkx`, `sympy`, `mpmath`, `filelock`, `fsspec`, `more-itertools`, `regex` (these are all transitive deps of the removed packages with no other user).

**Files to modify:** `backend/requirements.txt`  
**Verify:** `python -m pytest backend/tests/ -v --tb=short` from `backend/` — all tests pass. (The test suite does not import any removed package.) Optionally `pip install -r requirements.txt` in a fresh venv to confirm no missing transitive dependencies.

---

## STAGE 6 — Code Quality: Knowledge Service Logging (P2-5)

**What to do:**  
In `backend/services/knowledge_service.py`, the `except Exception:` block in `get_technology()` silently swallows JSON parse failures and returns a fallback dict. Add a `print()` statement before the return so failures are visible in the server log.

**Exact change in `knowledge_service.py`:**  
Find the `except Exception:` block (currently contains only `return {...}`). Add a `print()` call as the first line of the block:

```python
    except Exception as e:
        print(f"[knowledge_service] JSON parse error for technology='{technology}': {e}")
        return {
            "title": technology,
            ...
        }
```

Rename the bare `except Exception:` to `except Exception as e:` to capture the exception for the message. The return value is unchanged.

The `print()` prefix `[knowledge_service]` matches the server-log style used elsewhere in the codebase (e.g. `[ProviderRouter]` in `provider_router.py`).

**No new tests needed** for this change (it only adds a print; the logic is unchanged). Confirm the existing tests in `test_api.py` and the full suite still pass.

**Files to modify:** `backend/services/knowledge_service.py`  
**Verify:** `python -m pytest backend/tests/ -v --tb=short` — all tests pass.

---

## STAGE 7 — Code Quality: Debug Mode from Environment Variable (P2-6)

**What to do:**  
In `backend/app.py`, in the `if __name__ == '__main__':` block, replace the hardcoded `debug=True` with a value read from `FLASK_DEBUG`. Default is `'true'` so local development is unaffected.

**Exact change in `app.py`:**  
Find the `app.run(debug=True, threaded=True, ...)` call (at the bottom of the file). Replace:

```python
    app.run(debug=True, threaded=True, reloader_type="stat", exclude_patterns=[
```

with:

```python
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode, threaded=True, reloader_type="stat", exclude_patterns=[
```

`os` is already imported at the top of `app.py`.

**Also update `backend/.env.example`:**  
Append the following comment block before the last blank line:

```
# Flask debug mode (auto-reloader and detailed errors). Default: true for local dev.
# Set to false in production.
# FLASK_DEBUG=false
```

**No new tests needed** for this change (the `__main__` block is not exercised in the test suite; it is a startup-time configuration). Confirm the full test suite still passes.

**Files to modify:** `backend/app.py`, `backend/.env.example`  
**Verify:** `python -m pytest backend/tests/ -v --tb=short` — all tests pass.

---

## STAGE 8 — Code Quality: Fix Deprecated tempfile.mktemp() (P3-5)

**What to do:**  
In `backend/tests/_testenv.py`, the `fresh_database()` helper uses `tempfile.mktemp()` which is deprecated (creates a race condition between name generation and file creation). Replace it with a deterministic path under the already-created `_tmpdir`.

**Exact change in `_testenv.py`:**  
Find this line inside `fresh_database()`:

```python
    path = tempfile.mktemp(suffix=".db", dir=_tmpdir)
```

Replace with:

```python
    path = os.path.join(_tmpdir, f"expertos_test_{os.getpid()}_{int(time.monotonic() * 1e6)}.db")
```

Use `time.monotonic()` rather than PID alone because multiple `fresh_database()` calls in the same process (same PID) must produce distinct paths. `os` and `tempfile` are already imported. Add `import time` to the imports at the top of `_testenv.py` if not already present. (Currently `_testenv.py` does not import `time`.)

**Note on the top-level `_tmpdir` usage:**  
The top-level `_tmpdir = tempfile.mkdtemp(...)` call in the module body is correct (`mkdtemp` is safe — it creates the directory atomically) and must not be changed.

**Files to modify:** `backend/tests/_testenv.py`  
**Verify:** `python -m pytest backend/tests/ -v --tb=short` — all tests pass with no `DeprecationWarning` for `mktemp`.

---

## STAGE 9 — Final Verification

**What to do:**  
Run the complete backend test suite and the frontend build/test suite to confirm no regressions across all 8 stages combined.

**Backend:**

```
cd c:\Users\shaha\OneDrive\Desktop\ExpertOS-kiro\backend
python -m pytest tests/ -v --tb=short
```

Expected: all tests pass. Acceptable: previously-skipped or expected-fail tests remain in their prior state. Not acceptable: any test that passed before stage 1 now fails.

**Frontend (TypeScript + build check):**

```
cd c:\Users\shaha\OneDrive\Desktop\ExpertOS-kiro\frontend
npm run build
npm test
```

Expected: clean build, tests pass. The frontend was not modified in any stage (only `backend/.env.example` was touched, and that has no effect on the frontend build).

**Files to modify:** None (verification only).  
**Stop condition:** If any test fails that was passing before Stage 1, do not proceed to Stage 10 — diagnose and fix the regression first.

---

## STAGE 10 — Git Commit

**What to do:**  
Create a git checkpoint by staging all modified files and committing them with the specified message.

**Files modified across all stages:**
- `backend/app.py` (stages 1, 2, 7)
- `backend/providers/ollama_provider.py` (stage 3)
- `backend/providers/gemini_provider.py` (stage 4)
- `backend/requirements.txt` (stage 5)
- `backend/services/knowledge_service.py` (stage 6)
- `backend/.env.example` (stage 7)
- `backend/tests/_testenv.py` (stage 8)
- `backend/tests/test_api.py` (stages 1, 2)
- `backend/tests/test_provider_fallback.py` (stages 3, 4)

**Commands:**

```
cd c:\Users\shaha\OneDrive\Desktop\ExpertOS-kiro

git add backend/app.py backend/providers/ollama_provider.py backend/providers/gemini_provider.py backend/requirements.txt backend/services/knowledge_service.py backend/.env.example backend/tests/_testenv.py backend/tests/test_api.py backend/tests/test_provider_fallback.py

git commit -m "improve: P1/P2/P3 engineering improvements from technical audit"
```

If git is not yet initialized in this workspace, run `git init` first, then stage and commit.

**Verify:** `git log --oneline -1` shows the commit message. `git diff HEAD~1 --stat` shows only the 9 expected files changed.

---

## Cross-Cutting Notes for the Implementer

### Auth pattern (stages 1–2)
`auth.require_owner(_owner())` raises `auth.Forbidden` (HTTP 403) — not 401 — when the browser sends no `X-Client-Id` and has no session. The test client in `_testenv.py` injects `HTTP_X_CLIENT_ID` by default. To test the unauthenticated case, call `_testenv.client(app, client_id=None)` which omits the header. The `auth.Forbidden` error is handled by `handle_app_error` and returns `{"error": "..."}` with 403 — not 401. Check the actual status code; the plan above says 401 generically but the real code raises `Forbidden`. Update the test assertion to match the actual Flask error handler response (`403`, not `401`), or check what `auth.require_owner` actually raises: looking at `auth.py` it raises `Forbidden` (status 403), not `Unauthorized` (status 401). The test should assert `status_code == 403`.

### Ollama test for HTTP 500 (stage 3)
To simulate `raise_for_status()` raising an `HTTPError`, build the mock carefully:
```python
mock_response = mock.Mock()
mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
    response=mock.Mock(status_code=500)
)
mock_response.json.return_value = {}
self.requests_post.return_value = mock_response
```

### requirements.txt format (stage 5)
The file has a mix of pinned versions (`Flask==3.1.2`) and unpinned entries (`groq`, `google-generativeai`, `truststore>=0.10`, `pypdf>=5`). Remove complete lines. The comment lines (`# AI provider SDKs...`, `# Verify HTTPS...`, `# Text extraction...`) must be kept with their associated packages.

### No re-architecture
None of these stages change any data model, API contract, streaming format, expert prompt, or frontend code. If an unexpected issue arises that would require changing any of those, stop and report before proceeding.
