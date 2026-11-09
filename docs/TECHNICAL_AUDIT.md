# ExpertOS — Comprehensive Technical Audit

**Date:** 2025  
**Auditor:** Kiro AI Technical Audit Agent  
**Scope:** Full read-only review of all backend and frontend source files  
**Status:** READ-ONLY — no files were modified

---

## Table of Contents

1. [System Overview & Architecture](#1-system-overview--architecture)
2. [Complete API Endpoint Inventory](#2-complete-api-endpoint-inventory)
3. [Database Schema Documentation](#3-database-schema-documentation)
4. [Expert Configuration Inventory](#4-expert-configuration-inventory)
5. [AI Infrastructure Analysis](#5-ai-infrastructure-analysis)
6. [Security Findings](#6-security-findings)
7. [Reliability Findings](#7-reliability-findings)
8. [Performance Findings](#8-performance-findings)
9. [Code Quality Findings](#9-code-quality-findings)
10. [Conversation Management Findings](#10-conversation-management-findings)
11. [Prioritized Improvement Roadmap](#11-prioritized-improvement-roadmap)
12. [Changes Safe to Implement Independently](#12-changes-safe-to-implement-independently)
13. [Changes Requiring Owner Approval](#13-changes-requiring-owner-approval)

---

## 1. System Overview & Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (React 19)                        │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ExpertRoom│ │Consultation│ │ExpertPanel│ │LiveDiscussion    │ │
│  │ /expert/:│ │/consultation│ │ /panel   │ │ (within panel)  │ │
│  │  id      │ │            │ │          │ │                  │ │
│  └──────────┘ └────────────┘ └──────────┘ └──────────────────┘ │
│                     fetch / SSE streams                          │
│         X-Client-Id header │ Authorization: Bearer token        │
└─────────────────────────────────────────────────────────────────┘
              │HTTP (default: http://127.0.0.1:5000)
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Flask Backend (app.py)                       │
│                                                                  │
│  Rate limiters (memory) │ CORS (flask-cors, wildcard)           │
│  Auth: X-Client-Id hash │ Bearer session token                  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Route Handlers                        │    │
│  │  /analyze  /chat  /expert/*  /panel  /live/*  /files    │    │
│  │  /conversations  /stats  /auth/*  /contact  /knowledge  │    │
│  └───────────────────┬─────────────────────────────────────┘    │
│                      │                                           │
│  ┌───────────────────▼─────────────────────────────────────┐    │
│  │                   Service Layer                          │    │
│  │  consultation_engine.py  │  panel_engine.py             │    │
│  │  live_engine.py          │  ai_provider.py              │    │
│  │  conversations.py        │  context.py                  │    │
│  │  auth.py                 │  files.py                    │    │
│  │  expert_manager.py       │  intent.py                   │    │
│  │  router.py               │  metrics.py                  │    │
│  └───────────────────┬─────────────────────────────────────┘    │
│                      │                                           │
│  ┌───────────────────▼─────────────────────────────────────┐    │
│  │               Provider Router                            │    │
│  │  providers/provider_router.py                           │    │
│  │  OpenRouter → Gemini → Groq → Ollama (fallback chain)   │    │
│  └───────────────────┬─────────────────────────────────────┘    │
│                      │                                           │
│  ┌───────────────────▼─────────────────────────────────────┐    │
│  │           SQLite (backend/data/expertos.db)              │    │
│  │  WAL mode │ foreign keys │ migrations │ row_factory      │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
              │outbound HTTPS
              ▼
┌───────────────────────────────────────────┐
│    AI Providers (external)                │
│  OpenRouter (openai SDK) → free models    │
│  Google Gemini (google-generativeai SDK)  │
│  Groq (groq SDK)                          │
│  Ollama (requests, local)                 │
└───────────────────────────────────────────┘
```

### 1.2 Component Summary

| Layer | Technology | Key Files |
|---|---|---|
| Frontend | React 19, Vite 8, Tailwind CSS 4, React Router 7 | `frontend/src/` |
| Backend | Python 3.12+, Flask 3.1, flask-cors 6 | `backend/app.py` |
| Database | SQLite (WAL), migrations via numbered .sql files | `backend/migrations/` |
| AI routing | Custom ProviderRouter, openai SDK to OpenRouter | `providers/`, `services/openrouter_client.py` |
| Auth | SHA-256 hashed tokens, Werkzeug scrypt passwords | `services/auth.py` |
| State (FE) | React local state + localStorage (session/clientId) + sessionStorage (active conv) | `services/identity.js` |

### 1.3 Key Data Flows

**Expert Room Flow:**
1. User fills discovery wizard → `POST /expert/discovery` (static, no AI)
2. Answers submitted → `POST /expert/recommend` → `generate_recommendation()` → AI → stores conversation
3. Follow-up chat → `POST /expert/chat/stream` (SSE) → `_expert_chat_request()` → role-switch check → `stream_ai()`
4. Expert switching resolved in `expert_manager.resolve_switch()` and `_expert_room_switch()` before the AI call

**Start Consultation Flow:**
1. Project description → `POST /analyze` → `analyze_project()` → AI → stores conversation
2. Follow-up → `POST /chat` → `consultation_engine.chat()` → concurrent routing + answering (ThreadPoolExecutor) → saves atomically

**Expert Panel Flow:**
1. `POST /panel` or `POST /panel/stream` → `iter_panel()` → ThreadPoolExecutor (up to 6 workers) → each expert concurrently → synthesis sequentially

**Live Room Flow:**
1. `POST /live/sessions` (creates, tied to panel consultation token)
2. `POST /live/sessions/:id/rounds` (SSE stream) → `live_engine.run_round()` → busy lock (DB column) → streams expert tokens

---

## 2. Complete API Endpoint Inventory

| Method | Path | Auth Required | Rate Limited | Purpose |
|---|---|---|---|---|
| GET | `/` | No | No | Health check (returns string) |
| GET | `/health` | No | No | JSON health check |
| POST | `/analyze` | Owner (client/user) | AI limiter | Start Consultation analysis |
| POST | `/chat` | Owner | AI limiter | Start Consultation follow-up |
| POST | `/expert/chat` | Optional | AI limiter | Expert Room chat (non-streaming) |
| POST | `/expert/chat/stream` | Optional | AI limiter | Expert Room chat (SSE streaming) |
| POST | `/panel` | None | AI limiter | Multi-expert panel (sync) |
| POST | `/panel/stream` | None | AI limiter | Multi-expert panel (SSE streaming) |
| POST | `/knowledge` | None | No | Technology explanation (AI) |
| POST | `/expert/discovery` | None | No | Discovery wizard steps (static) |
| POST | `/expert/recommend` | Owner | AI limiter | Expert Room recommendation |
| POST | `/expert/match` | None | No | AI Guide — suggest best expert (no AI) |
| POST | `/auth/register` | None | Register limiter | Create account |
| POST | `/auth/login` | None | Login limiter | Sign in |
| POST | `/auth/logout` | None | No | Sign out |
| GET | `/auth/me` | None (session optional) | No | Current user info |
| GET | `/conversations` | Owner | No | List saved conversations |
| GET | `/conversations/:id` | Owner | No | Get conversation detail |
| DELETE | `/conversations/:id` | Owner | No | Delete conversation |
| POST | `/files` | Owner | Upload limiter | Upload files |
| DELETE | `/files/:id` | Owner | No | Delete uploaded file |
| GET | `/stats` | None | No (15s cache) | Platform statistics |
| GET | `/stats/performance` | None | No | Detailed performance metrics |
| GET | `/consultations/:id/rating` | Token | No | Check if rated |
| POST | `/consultations/:id/rating` | Token | Rating limiter | Submit rating |
| DELETE | `/consultations/:id` | Token | No | Delete consultation content |
| POST | `/live/sessions` | Token | No | Open live session |
| GET | `/live/sessions/:id` | Token | No | Get live session state |
| POST | `/live/sessions/:id/rounds` | Token | No | Run live discussion round (SSE) |
| POST | `/live/sessions/:id/close` | Token | No | End live session + generate summary |
| POST | `/live/sessions/:id/summary` | Token | No | Retry summary generation |
| POST | `/contact` | None | Contact limiter | Submit contact form |

**Auth notes:**
- "Owner" means the request must carry either a valid `X-Client-Id` header (browser identity) or a valid `Authorization: Bearer <token>` session. Both are checked by `auth.require_owner()`.
- "Token" means the `X-Consultation-Token` header with the original consultation access token.
- Panel endpoints (`/panel`, `/panel/stream`) have **no owner/auth requirement** — any caller may run a panel with no identity.

---

## 3. Database Schema Documentation

### 3.1 Tables and Relationships

```
consultations (id PK)
    ├── ratings (consultation_id FK → consultations.id CASCADE)
    ├── live_sessions (consultation_id FK → consultations.id CASCADE)
    │       └── live_messages (session_id FK → live_sessions.id CASCADE)
    └── conversations.consultation_id FK → consultations.id SET NULL

users (id PK)
    ├── auth_sessions (user_id FK → users.id CASCADE)
    ├── conversations (user_id FK → users.id CASCADE)
    └── uploaded_files (user_id FK → users.id CASCADE)

conversations (id PK)
    ├── conversation_messages (conversation_id FK → conversations.id CASCADE)
    └── uploaded_files.conversation_id FK → conversations.id SET NULL

schema_migrations (version PK)
contact_messages (id PK)
operations (id PK)
ai_calls (id PK)
```

### 3.2 Table Definitions

#### `consultations`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| kind | TEXT | `expert_room`, `quick_consultation`, `panel` |
| expert_keys | TEXT | JSON list of expert key strings |
| status | TEXT | Always `completed` |
| token_hash | TEXT | SHA-256 of access token |
| problem | TEXT | Nullable; purged after CONTENT_RETENTION_DAYS (30d) |
| result_json | TEXT | Panel results; purged after retention |
| created_at | TEXT | ISO-8601 UTC |
| content_deleted_at | TEXT | Set when content purged |

Indexes: `idx_consultations_status_created (status, created_at)`

#### `ratings`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| consultation_id | TEXT UNIQUE FK | One rating per consultation |
| stars | INTEGER | 1–5 |
| feedback | TEXT | Optional |
| created_at | TEXT | |

#### `users`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| email | TEXT UNIQUE | Lower-cased |
| name | TEXT | Nullable |
| password_hash | TEXT | Werkzeug scrypt hash |
| created_at | TEXT | |
| last_login_at | TEXT | Nullable |

#### `auth_sessions`
| Column | Type | Notes |
|---|---|---|
| token_hash | TEXT PK | SHA-256 of bearer token |
| user_id | TEXT FK | → users.id CASCADE |
| created_at | TEXT | |
| expires_at | TEXT | Compared against utc_now() |

Index: `idx_auth_sessions_user (user_id)`

#### `conversations`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| kind | TEXT | `expert_room` or `quick_consultation` |
| user_id | TEXT FK | Nullable; → users.id CASCADE |
| client_hash | TEXT | SHA-256 of X-Client-Id |
| expert_key | TEXT | Room's original expert key (never changes) |
| active_expert | TEXT | Current chatbot role (changes on switch) |
| title | TEXT | |
| project | TEXT | |
| answers_json | TEXT | Discovery wizard answers |
| report_json | TEXT | Recommendation or analysis |
| consultation_id | TEXT FK | Nullable; → consultations.id SET NULL |
| created_at | TEXT | |
| updated_at | TEXT | |

Indexes: `idx_conversations_user (user_id, updated_at)`, `idx_conversations_client (client_hash, updated_at)`

#### `conversation_messages`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | Ordering key |
| conversation_id | TEXT FK | → conversations.id CASCADE |
| role | TEXT | `user`, `expert`, `system` |
| expert_key | TEXT | Nullable |
| content | TEXT | |
| file_ids | TEXT | JSON list |
| created_at | TEXT | |

Index: `idx_conversation_messages_conv (conversation_id, id)`

#### `uploaded_files`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| user_id | TEXT FK | Nullable; → users.id CASCADE |
| client_hash | TEXT | |
| conversation_id | TEXT FK | Nullable; → conversations.id SET NULL |
| filename | TEXT | Display only; sanitized |
| content_type | TEXT | MIME type |
| size_bytes | INTEGER | |
| kind | TEXT | `document` or `image` |
| storage_name | TEXT | Random hex name under `backend/data/uploads/` |
| extracted_text | TEXT | What the AI reads |
| extraction_note | TEXT | Truncation/scan warnings |
| created_at | TEXT | |

Indexes: `idx_uploaded_files_owner (user_id, client_hash)`, `idx_uploaded_files_conversation (conversation_id)`

#### `live_sessions`
| Column | Type | Notes |
|---|---|---|
| id | TEXT PK | UUID |
| consultation_id | TEXT FK | → consultations.id CASCADE |
| status | TEXT | `active` or `closed` |
| stage | INTEGER | Agenda index (0–4) |
| rounds | INTEGER | Increments per round |
| busy_since | TEXT | Cross-process lock timestamp |
| summary_json | TEXT | Key Takeaways JSON |
| summary_error | TEXT | |
| created_at | TEXT | |
| closed_at | TEXT | |

Index: `idx_live_sessions_consultation (consultation_id)`

#### `live_messages`
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| session_id | TEXT FK | → live_sessions.id CASCADE |
| seq | INTEGER | Message order (UNIQUE per session) |
| role | TEXT | `expert`, `client`, `system` |
| expert_key | TEXT | Nullable |
| content | TEXT | |
| client_message_id | TEXT | Idempotency key (UNIQUE per session) |
| created_at | TEXT | |
| agenda_stage | INTEGER | Added in migration 004; nullable |

Unique constraints: `(session_id, seq)`, `(session_id, client_message_id)`

#### `operations` / `ai_calls`
Response-time measurements only; no conversation text is stored.

#### `contact_messages`, `schema_migrations`
Standard as described in README.

---

## 4. Expert Configuration Inventory

Expert data lives in two places: `backend/data/experts.json` (loaded by `services/expert_manager.py`) and `frontend/src/data/experts.js` (display profiles). They are separate but consistent.

| Backend Key | Name | Role | Frontend ID |
|---|---|---|---|
| Software Architect | Ethan Walker | Senior Software Architect | `ethan` |
| Design Advisor | Maya Chen | Senior Product Designer | `maya` |
| Database Engineer | Alex Morgan | Database Engineer | `alex` |
| Security Expert | Sarah Patel | Cyber Security Consultant | `sarah` |
| Cloud Consultant | Daniel Brooks | Cloud Infrastructure Consultant | `daniel` |
| DevOps Engineer | Ryan Cooper | DevOps Engineer | `ryan` |

### 4.1 Expert Identity Storage
- Backend: `backend/data/experts.json` — name, role, emoji, system persona description, expertise list
- Frontend: `frontend/src/data/experts.js` — id, icon (emoji), gradient color, display role, greeting text, analysis text, tags
- Mapping: `frontend/src/data/experts.js` `profileFor(key)` maps a backend key to a frontend display profile

### 4.2 Expert Personality Application
- At AI call time, `services/ai_provider.py:build_chat_prompt()` constructs the full system prompt
- Expert's `name`, `role`, `expertise` fields are injected into the prompt
- Conversation history, project context, files, and intent classification all shape the prompt
- The expert is told explicitly who they are, what they have access to, and what kind of reply is needed

---

## 5. AI Infrastructure Analysis

### 5.1 Provider Fallback Chain

Order: **OpenRouter** → **Gemini** → **Groq** → **Ollama**

Each provider is tried at most once per request. Provider-wide failures (auth, credits, account quota, TLS, connection) immediately stop trying further models on that provider and move to the next. Transient failures (rate limit, timeout, server error, empty/malformed response) fall through to the next provider without cooldown.

#### OpenRouter
- File: `services/openrouter_client.py`
- Uses OpenAI SDK pointed at `https://openrouter.ai/api/v1`
- Internal model registry: Gemma 4 31B → Gemma 4 26B → Nemotron 3.5 Lightning → OpenRouter Free Router
- Per-model health tracking with 60-second cooldown after 2 failures; 1800-second cooldown for 404/403
- Retry same model up to 2 times for SERVER/CONNECTION errors with exponential backoff
- Truncated-answer retry: doubles token budget once if answer cut off before any content
- Streaming: model fallback only allowed before first token is sent; partial streaming raises `partial=True` error
- Vision models: separate list used when images are attached

#### Gemini
- File: `providers/gemini_provider.py`
- Uses `google-generativeai` SDK with REST transport (avoids gRPC retry loops)
- 45-second timeout
- `THINKING_HEADROOM = 2048` added to max_tokens because gemini-2.5-flash reasons internally
- MAX_TOKENS finish_reason raises ProviderError(EMPTY) — provider router tries next provider
- No streaming support; falls back to generate-then-yield pattern in provider_router.py

#### Groq
- File: `providers/groq_provider.py`
- Uses `groq` SDK with 60-second timeout
- `REASONING_HEADROOM = 1024` for gpt-oss models that reason
- Lazy client instantiation to avoid startup crash when no API key
- No streaming support

#### Ollama
- File: `providers/ollama_provider.py`
- Uses `requests` (not an SDK) — raw HTTP POST to `/api/generate`
- Model: `deepseek-r1:8b`
- 120-second timeout
- No streaming support
- Does not propagate classified `ProviderError` — raises plain `Exception("Ollama Provider Error: ...")`

### 5.2 Provider Cooldown System
- Implemented in `providers/provider_router.py:ProviderRouter`
- In-memory `_cooldowns` dict: `{name: (until, category, retry_at)}`
- Thread-safe with `threading.Lock()`
- Cooldown durations: ACCOUNT_LIMIT 600s (or reported reset time), CREDITS/AUTH/FORBIDDEN/MODEL_NOT_FOUND 1800s, TLS 600s, CONNECTION 120s
- Maximum cooldown: 24 hours
- Transient failures (RATE_LIMIT, TIMEOUT, SERVER, EMPTY, MALFORMED, UNKNOWN) do NOT trigger provider-level cooldown

### 5.3 Token/Context Management
- File: `services/context.py`
- Recent messages: last 12 in full (up to 4000 chars each)
- Older messages: condensed to 300 chars each, newest-first within a 16,000-char history budget
- Omitted messages are stated explicitly in the prompt ("N earliest messages not shown")
- Documents: 40,000-char budget shared across files; per-file share = max(4000, 40000 ÷ files)
- Truncation is labeled ("only first N of M characters included")
- Images listed separately; passed as base64 to vision-capable providers

### 5.4 Streaming Implementation
- SSE format: `event: <name>\ndata: <JSON>\n\n`
- OpenRouter: true streaming via OpenAI SDK `stream=True`
- Other providers: `generate()` result yielded as a single chunk
- Backend: `services/ai_provider.py:stream_ai()` → `provider_router.stream()` → `openrouter_client.stream()`
- Frontend: `services/api.js:streamSSE()` — ReadableStream with TextDecoder, `\n\n` block parsing
- Partial-reply preservation: if streaming breaks after first token, the partial text is kept on screen marked `[Reply interrupted]`
- Slow-response indicator: shown after 30 seconds; hard timeout after 150 seconds client-side

### 5.5 Metrics Recording
- Every AI call recorded in `ai_calls` table (provider, model, timing, success, attempts)
- Every user-facing operation recorded in `operations` table
- `provider_attempts` JSON column records the full fallback trail per call
- Metrics recording is fire-and-forget: storage errors logged and ignored (never break a request)

---

## 6. Security Findings

### 6.1 CRITICAL — Live API Keys in Accessible File

**Severity:** CRITICAL  
**File:** `backend/.env`  
**Issue:** The `.env` file contains live OpenRouter, Gemini, and Groq API keys. The `.gitignore` correctly excludes `.env`, so the keys are not in any git repository at this time. However, the file exists in the project workspace on disk. If this workspace folder were ever pushed to a public or shared repository, shared via cloud sync without access controls, or accessed by an unauthorized party, these keys would be fully exposed.

**Current State:**
- `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY` are present with real values
- `.gitignore` in `backend/` lists `.env` — correct
- No git repository exists yet for this workspace

**Risk:** Key exposure allows unauthorized AI quota consumption, financial charges on the account, and potential data access.

**Recommended Actions (before initializing git or sharing this folder):**
1. Rotate all three API keys immediately at their respective provider dashboards
2. Confirm `backend/.env` is in `.gitignore` before `git init` (it is — verified)
3. Never commit `.env`; use environment variables or a secrets manager in production
4. Consider adding a `gitleaks` or `trufflehog` pre-commit hook

---

### 6.2 HIGH — CORS Configured with Wildcard (All Origins Allowed)

**Severity:** High  
**File:** `backend/app.py`, line: `CORS(app)`  
**Issue:** `flask-cors` is initialized with no `origins` argument, which defaults to allowing all origins (`*`). This means any website can make credentialed requests to the backend API from a visitor's browser.

**Current State:**
```python
CORS(app)  # app.py — no origins restriction
```

**Risk:** Any site could trigger AI calls, consume rate-limit quota, or attempt to probe session tokens. For a public API this is often acceptable, but combined with the memory-only rate limiter (one process), a cross-origin abuse script could exhaust per-IP quota.

**Proposed Fix:** Restrict to the known frontend origin:
```python
CORS(app, origins=["http://localhost:5173", "https://your-production-domain.com"])
```
Or read from env: `CORS_ORIGINS` env var.

---

### 6.3 HIGH — Rate Limiters Are In-Memory Per-Process (Not Scalable)

**Severity:** High (operational, not a bypass vulnerability for single-process deployment)  
**Files:** `backend/app.py` lines 75–87 (RateLimiter class and instantiation)  
**Issue:** All rate limiters (`ai_limiter`, `login_limiter`, `register_limiter`, `upload_limiter`, `rating_limiter`, `contact_limiter`) store their sliding windows in process memory. On a multi-process deployment (e.g., gunicorn with multiple workers), each process has its own counters and the per-IP limit is effectively multiplied by the number of workers.

**Also noted in README:** "Rate limits... are kept in memory per process. Run a single backend process, or move them to a shared store, before scaling out."

**Risk:** Scripted abuse can bypass rate limits by spreading requests across multiple worker processes. Also, a server restart resets all counters.

**Proposed Fix (medium-term):** Replace with a Redis-backed sliding window (e.g., `redis-py` + a Lua script), or use Flask-Limiter with a Redis storage backend. This is a known limitation documented in the README and requires infrastructure changes.

---

### 6.4 HIGH — Panel Endpoints Have No Authentication or Identity

**Severity:** High  
**File:** `backend/app.py`, `POST /panel` and `POST /panel/stream`  
**Issue:** Both panel endpoints call `_panel_request()`, which parses the body but calls no auth check. Any request — from any origin, with no session, no client ID — can run a multi-expert panel consultation and consume AI quota.

**Current State:** `/analyze` and `/expert/recommend` call `auth.require_owner(_owner())` which enforces a client ID or session. `/panel` has no such call.

**Risk:** Unlimited panel calls from anonymous clients, consuming AI quota without any identity tracking.

**Proposed Fix:** Add `owner = auth.require_owner(_owner())` to `_panel_request()`, consistent with `/analyze`. This does not require a user account — it only requires the browser to send `X-Client-Id`, which the frontend already does.

---

### 6.5 MEDIUM — `/knowledge` Endpoint Has No Auth or Rate Limiting

**Severity:** Medium  
**File:** `backend/app.py`, route `/knowledge`  
**Issue:** The `/knowledge` endpoint calls an AI provider (`get_technology()`) but has no ownership check and is not covered by the `_ai_rate_limited()` call. Any caller can trigger knowledge generation.

**Proposed Fix:** Add `_ai_rate_limited()` check (same as other AI endpoints) and optionally `auth.require_owner()`.

---

### 6.6 MEDIUM — File Upload: No Virus/Malware Scanning

**Severity:** Medium  
**File:** `backend/services/files.py`  
**Issue:** Uploaded files are type-checked from content (magic bytes for images; ZIP/PDF structure for documents) and text is extracted. However, there is no malware scan. A valid PDF could carry embedded scripts; a ZIP could contain path-traversal filenames.

**Mitigations already in place:**
- Content-type detection from bytes, not just filename extension (lines 179–185)
- `_safe_display_name()` sanitizes the filename (strips path separators, control chars)
- Files are stored under random UUIDs and never served back
- Extracted text only is passed to the AI — not the original binary

**Remaining risk:** Denial-of-service via deeply nested ZIPs or ZIP bombs (MAX_ZIP_MEMBERS=60 and MAX_ZIP_TEXT_BYTES=5MB mitigate but don't eliminate this). Malicious macros in .docx/.xlsx are not executed, but they are silently included in the ZIP structure.

**Proposed Fix:** Add `zipfile.is_zipfile()` check before opening ZIPs; enforce compressed-to-uncompressed ratio (zip bomb detection). Consider `python-magic` for more robust MIME detection.

---

### 6.7 MEDIUM — Consultation Token Sent as Header, Not Validated Consistently

**Severity:** Medium  
**Files:** `backend/app.py` (TOKEN_HEADER, `_token()`), `backend/services/consultations.py:get_authorized()`  
**Issue:** The consultation access token in `X-Consultation-Token` provides access to ratings, deletion, and live room sessions. `get_authorized()` uses `hmac.compare_digest()` for timing-safe comparison — correct. However, the token is logged in server logs when Flask prints request details in debug mode, since it appears in the response headers area. More importantly: the token is never rotated after use.

**Mitigations already in place:** Token is passed as a header, not in the URL, so it doesn't appear in server access logs or browser history.

**Proposed Fix:** No immediate code change needed; note that tokens should not be rotated since the frontend stores them in localStorage (`consultations.js`) to reopen sessions. Low priority.

---

### 6.8 MEDIUM — Email Validation Is a Minimal Regex

**Severity:** Medium  
**Files:** `backend/app.py` (EMAIL_RE for contact form), `backend/services/auth.py` (EMAIL_RE for accounts)  
**Issue:** Both use the same simple regex `r"^[^@\s]+@[^@\s]+\.[^@\s]+$"`. This accepts some technically invalid addresses and rejects some valid internationalized ones. More importantly, there is no email domain validation or verification.

**Risk:** Account creation with a fake email (no password reset possible anyway since there's no email service — acknowledged in README). Low operational risk given the no-email-service constraint.

---

### 6.9 LOW — Session Tokens Stored in localStorage

**Severity:** Low  
**File:** `frontend/src/services/identity.js`  
**Issue:** The session bearer token is stored in `localStorage`. XSS attacks can steal localStorage content. HttpOnly cookies would not be accessible via JavaScript.

**Mitigations already in place:** CORS is wide-open (reducing the cookie CSRF protection value), and `sessionStorage` is used for the active conversation state rather than the token.

**Proposed Fix (requires review):** Migrating to HttpOnly cookies would require Flask to set `Set-Cookie` and the frontend to stop sending `Authorization: Bearer`. This is a meaningful architectural change that affects both auth flows.

---

### 6.10 LOW — No CSRF Protection

**Severity:** Low (mitigated by CORS and token headers)  
**Issue:** No CSRF tokens. The API uses `Content-Type: application/json` and custom headers (`X-Client-Id`), which browsers won't send in simple cross-origin form submissions. Combined with CORS, this provides reasonable CSRF protection without explicit tokens.

---

## 7. Reliability Findings

### 7.1 HIGH — `consultation_engine.py` Speculative Answer May Be Discarded, Wasting a Token

**File:** `backend/services/consultation_engine.py` lines 82–107  
**Issue:** The engine runs routing and the expert's answer concurrently. When the router decides to switch, the speculative answer is discarded. This is by design for speed, but means a full AI call is wasted on every successful switch — consuming provider quota and adding to response time.

**Impact:** Not a data-loss risk (the answer is simply unused); a cost-efficiency issue. Worst case: double AI call overhead on switches.

---

### 7.2 HIGH — Live Engine `busy_since` Lock Can Become Stale if Process Crashes

**File:** `backend/services/live_engine.py`, `_acquire()` / `_release()`  
**Issue:** The cross-request lock is a timestamp column. If the backend crashes mid-round, `busy_since` is never cleared. The stale timeout is `LOCK_STALE_SECONDS = 300` (5 minutes). During those 5 minutes, all round requests will fail with "The experts are still responding."

**Risk:** A crash during a live discussion locks users out for up to 5 minutes. This is acceptable for a single-process dev deployment but worth noting for production.

**Mitigations already in place:** Stale detection after 5 minutes; `_release()` wrapped in try/except to attempt cleanup even on error.

---

### 7.3 MEDIUM — Ollama Provider Does Not Raise `ProviderError`

**File:** `backend/providers/ollama_provider.py`  
**Issue:** All exceptions are caught and re-raised as `Exception("Ollama Provider Error: {e}")`. The `classify_exception()` function in `errors.py` handles plain `Exception` via string inspection — but "Ollama Provider Error" won't match any specific classification, so all Ollama failures are classified as `UNKNOWN`.

**Impact:** Cooldown for Ollama failures is always for category UNKNOWN, which has `COOLDOWN_SECONDS = None` — meaning Ollama is **never cooled down** even for persistent failures like "connection refused". Every request will attempt Ollama again.

**Proposed Fix:** Wrap the `requests` call to raise `ProviderError` with the correct category (CONNECTION for connection errors, TIMEOUT for timeouts).

---

### 7.4 MEDIUM — Gemini Provider Does Not Support Streaming

**File:** `backend/providers/gemini_provider.py`  
**Issue:** Gemini has no `stream` key in its provider entry. When Gemini is the only available provider (or OpenRouter is in cooldown), the Expert Room streaming UI will receive the full text as a single chunk rather than streaming tokens. This degrades the perceived experience but does not lose data.

**Proposed Fix:** Implement streaming via `model.generate_content(..., stream=True)` with the Gemini SDK's stream iterator.

---

### 7.5 MEDIUM — `purge_expired_content()` Called on Every Consultation Create

**File:** `backend/services/consultations.py:create_consultation()` (last line)  
**Issue:** `purge_expired_content()` runs a DELETE and several SELECTs on every new consultation. On an installation with thousands of consultation records, this adds latency to every consultation completion. The purge uses `BEGIN IMMEDIATE` which may briefly block concurrent writers.

**Proposed Fix:** Move purge to a background thread or a scheduled job (e.g., run at startup and then once per day). The purge is idempotent so occasional misses are safe.

---

### 7.6 MEDIUM — `conversation.purge_expired()` Called on Every `create()` 

**File:** `backend/services/conversations.py:create()` (last line)  
Same pattern as 7.5. Both purges run on a write path.

---

### 7.7 LOW — Panel Engine ThreadPoolExecutor Is Module-Level but Not Reused

**File:** `backend/services/consultation_engine.py`  
**Issue:** `_executor` is a module-level `ThreadPoolExecutor(max_workers=8)` that persists across requests — correct and efficient. However, `panel_engine.py` creates a new `ThreadPoolExecutor` inside each `iter_panel()` call with `executor.shutdown(wait=False)`. The `wait=False` means threads continue running after the function returns; in high-traffic scenarios, this could lead to thread accumulation.

**Proposed Fix:** Use a module-level executor in `panel_engine.py` as well, with a bounded queue.

---

### 7.8 LOW — Live Room `close_session()` Busy-Polls the Database

**File:** `backend/services/live_engine.py:close_session()` lines 330–337  
**Issue:** After marking the session as closed, the function polls `busy_since` every 0.5 seconds for up to 90 seconds. This is a blocking spin-poll on the Flask request thread, which holds a connection thread for that duration.

**Impact:** In a multi-user scenario, several simultaneous "End & Summarize" requests could exhaust the Flask thread pool. With Flask's default debug server this is low risk; on gunicorn it could be a concern.

**Proposed Fix:** Move summarization to a background task and return immediately with a 202 Accepted, letting the client poll for completion.

---

## 8. Performance Findings

### 8.1 MEDIUM — No Database Indexes on `conversation_messages.created_at`

**File:** `backend/migrations/003_accounts_conversations_files.sql`  
**Issue:** Messages are queried with `ORDER BY id` (correct for ordering), but the `created_at` column has no index. If filtering by date range were needed, this would require a full table scan. Currently no date-filtered queries on `conversation_messages` exist, so this is low impact but worth noting for future features.

---

### 8.2 MEDIUM — `conversations.list_for()` Uses a Correlated Subquery for Message Count

**File:** `backend/services/conversations.py:list_for()` lines 117–128  
**Issue:** The query includes:
```sql
(SELECT COUNT(*) FROM conversation_messages m WHERE m.conversation_id = c.id AND m.role != 'system') AS message_count
```
This executes one subquery per conversation row returned. For a user with 50 conversations (the LIST_LIMIT), this is 50 extra queries. SQLite may optimize this as a join-aggregate, but it's not guaranteed.

**Proposed Fix:** Join and GROUP BY, or store message count in the `conversations` table and increment/decrement it.

---

### 8.3 MEDIUM — `platform_stats()` Joins Consultations and Ratings Without Index on `ratings.consultation_id`

**File:** `backend/services/consultations.py:platform_stats()`  
**Issue:**
```sql
SELECT c.expert_keys, r.stars FROM consultations c LEFT JOIN ratings r ON r.consultation_id = c.id WHERE c.status = 'completed'
```
`ratings.consultation_id` is `UNIQUE` (which SQLite indexes automatically for uniqueness enforcement) — so this is actually fine. The UNIQUE constraint creates an implicit index. **No issue.**

---

### 8.4 MEDIUM — `uploaded_files` Content Is Read on Every Expert Reply

**File:** `backend/services/files.py:list_for_conversation()` called by `conversations.detail()`  
**Issue:** Every chat reply fetches all files for the conversation from the database, including their `extracted_text` column, which can be up to 200,000 characters per file. With 5 files at max extraction size (1MB of text per file), each chat reply fetches up to 5MB of text from SQLite before passing to `documents_section()`. The text is then truncated to 40,000 chars anyway.

**Proposed Fix:** Query only files where `kind = 'document'` and limit `extracted_text` retrieval, or store an index of what's needed. Alternatively, truncation could happen at storage time.

---

### 8.5 LOW — React Component `ExpertRoom.jsx` Is a Large Monolithic File

**File:** `frontend/src/pages/ExpertRoom.jsx`  
**Issue:** The file contains `ExpertRoom`, `ExpertStatTiles`, and `ExpertRoomSession` components plus all state logic in ~350 lines. While not causing a performance problem, it reduces maintainability.

---

### 8.6 LOW — `useConversationList` Refreshes on Every Sign-In/Sign-Out Event

**File:** `frontend/src/services/history.js:useConversationList()`  
**Issue:** The hook listens for `expertos:session` events and bumps version, triggering a full list re-fetch on every auth state change. This is correct behavior but fires an additional API call when multiple components use `useConversationList` simultaneously (e.g., the Expert Room history panel).

---

### 8.7 LOW — `stats` Response Is Cached 15 Seconds But Has No Cache-Control on Performance Endpoint

**File:** `backend/app.py`, `/stats` vs `/stats/performance`  
**Issue:** `/stats` sets `Cache-Control: public, max-age=15`. `/stats/performance` has no cache header and may be called frequently by monitoring tools.

---

## 9. Code Quality Findings

### 9.1 MEDIUM — `router.py` Makes an Extra AI Call for Every Chat Message

**File:** `backend/services/router.py:ConsultationRouter.route()`  
**Issue:** For Start Consultation follow-ups, the router makes a separate AI call to decide if an expert switch is needed, in addition to the expert's answer call. This doubles AI costs for the routing step. The routing prompt uses `max_tokens=300` and a specialized prompt. While the routing is run concurrently with the answer (in `consultation_engine.py`), both calls consume quota.

**Context:** The Expert Room does not use this router — it uses `expert_manager.resolve_switch()` (keyword matching only). The Start Consultation uses this AI router as an additional signal on top of keyword matching.

**Impact:** Extra cost per chat message. Worth revisiting whether the AI router adds enough accuracy over pure keyword matching to justify the cost.

---

### 9.2 MEDIUM — `requirements.txt` Contains Many Unused Dependencies

**File:** `backend/requirements.txt`  
**Issue:** The requirements file contains dozens of packages that appear unused by the ExpertOS codebase:

- `fastapi==0.118.0`, `uvicorn==0.37.0`, `starlette==0.48.0` — ExpertOS uses Flask, not FastAPI
- `openai-whisper==20250625`, `whisper==1.1.10` — no audio transcription feature found
- `torch==2.8.0`, `transformers==4.56.2`, `tokenizers==0.22.1`, `huggingface-hub==0.35.1` — PyTorch and Hugging Face, no local model inference found
- `google-cloud-dialogflow==2.41.2` — not imported anywhere
- `tiktoken==0.12.0` — not imported anywhere
- `numba==0.62.1`, `llvmlite==0.45.1` — numerical computing, not used
- `SQLAlchemy==2.0.45`, `PyMySQL==1.1.2` — ExpertOS uses sqlite3 directly
- `google-genai==2.10.0` — the app uses `google-generativeai`, not `google-genai`

**Impact:** Very large installation footprint (torch alone is ~2.5GB). Slow `pip install`, increased attack surface, dependency conflicts. This is likely leftover from an earlier experimental phase.

**Proposed Fix:** Trim to actual dependencies:
```
Flask==3.1.2
flask-cors==6.0.5
python-dotenv==1.2.1
openai==1.109.1
google-generativeai
groq
requests==2.32.5
Werkzeug==3.1.4
pypdf>=5
truststore>=0.10
```

---

### 9.3 MEDIUM — `knowledge_service.py` Has No Auth, Rate Limiting, or JSON Fallback Logging

**File:** `backend/services/knowledge_service.py`  
**Issue:** The `get_technology()` function silently returns a "Unable to load" placeholder when JSON parsing fails. This hides errors from the operator. The exception is caught but not logged.

**Proposed Fix:** Add `print()` logging on parse failure, consistent with the pattern in other services.

---

### 9.4 MEDIUM — Consultation Router Response Validation Is Fragile

**File:** `backend/services/router.py`  
**Issue:** The router checks `result.get("next_expert") not in expert_manager.get_all_experts()` to validate the AI's response. It does NOT validate the `"switch"` key type, so if the AI returns `"switch": "true"` (a string), the check `result.get("switch")` would still be truthy. The check also calls `get_all_experts()` on every validation, loading all experts.

---

### 9.5 LOW — `gemini_provider.py` Has Inconsistent Error Handling

**File:** `backend/providers/gemini_provider.py`  
**Issue:** Non-`ProviderError` exceptions are caught and re-raised as `Exception("Gemini Provider Error: {e}")` — same pattern as the Ollama provider. Unlike the Ollama provider, the Gemini SDK raises typed exceptions (`google.api_core.exceptions.*`) that `classify_exception()` can handle correctly by checking HTTP status codes. But wrapping them in a plain `Exception` discards the status code, so `classify_exception()` falls back to `UNKNOWN` for some Gemini errors.

**Note:** The `test_provider_fallback.py` tests mock `generate_content` before this wrapping, so they test the classification logic correctly — but real Gemini errors would be mis-classified.

**Proposed Fix:** Remove the outer `except Exception as e: raise Exception(...)` wrapper; let typed SDK exceptions propagate to `ProviderError` classification.

---

### 9.6 LOW — Frontend Uses Array Index as React Key in Message Lists

**File:** `frontend/src/components/ExpertRoom/ExpertChat.jsx` line 183  
```jsx
{messages.map((msg, i) => (
  <MessageBubble key={i} msg={msg} expert={expert} />
))}
```
Using array index as `key` is a React anti-pattern when the array can be prepended or reordered (it can cause wrong animations and preserve stale state). For this append-only chat list it's functionally safe but not best practice.

---

### 9.7 LOW — `_testenv.py` Uses `tempfile.mktemp()` (Deprecated)

**File:** `backend/tests/_testenv.py` line 24  
`tempfile.mktemp()` is deprecated because it has a race condition. `tempfile.NamedTemporaryFile(delete=False)` or a unique path under the tmpdir is preferred.

---

### 9.8 LOW — Backend Debug Mode Enabled by Default

**File:** `backend/app.py` lines 176–185  
`app.run(debug=True, threaded=True, ...)` — debug mode is always on when running via `python app.py`. This exposes the Werkzeug debugger (which allows arbitrary code execution via the PIN-protected console, but the PIN is logged to stdout and visible to anyone with shell access).

**Proposed Fix:** Read from env: `debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"`.

---

## 10. Conversation Management Findings

### 10.1 STRONG — Context Isolation Is Correct

Expert conversations are strictly isolated:
- Each conversation has a `expert_key` (the room's expert) and `active_expert` (who is currently answering)
- `conversation_store.get()` validates both ownership AND kind — a conversation from Expert Room cannot be accessed via `/chat` (which requires `kind="quick_consultation"`)
- Switching experts in one room does NOT affect any other room or conversation (verified by test `test_switch_changes_only_the_chat_role_not_the_room`)
- The browser uses separate `sessionStorage` slots per room (`room.${expert.id}`) 

### 10.2 STRONG — Atomic Message Storage Prevents Half-Exchanges

**File:** `backend/services/conversations.py:add_messages()`  
User message and expert reply are stored together in a single `executemany` within one `BEGIN IMMEDIATE` transaction. A failed AI call leaves no dangling user message. This is a well-designed pattern.

### 10.3 MEDIUM — `conversation_messages` Has No Unique Constraint on User Input

**Issue:** While `live_messages` has an idempotency key (`client_message_id UNIQUE`) to prevent duplicate messages from retries, `conversation_messages` has no such mechanism. A network retry could result in duplicate messages if the response was received but the network connection dropped before the client saw it.

**Mitigating factor:** Messages are saved only after the AI reply is ready (add_messages is called with both the user message and reply together), so partial retries at the HTTP level won't produce duplicates as long as the client doesn't retry the request.

### 10.4 MEDIUM — Anonymous Conversation Retention Is Session-Storage Dependent on the Client

**File:** `frontend/src/services/history.js:activeConversation()`  
**Issue:** Active conversation IDs are stored in `sessionStorage`. If the user clears browser storage or opens a new browser tab, `sessionStorage` is empty and the conversation won't auto-restore. The conversation is still in the database and accessible via the history list, but the user won't see it re-appear automatically. This is expected behavior per the README ("clearing site data loses access") but can surprise users.

### 10.5 LOW — Expert Chat Without `conversation_id` Sends Full History from Client

**File:** `backend/app.py:_expert_chat_request()` (lines around 218–225)  
**Issue:** When no `conversation_id` is provided (stateless mode), the frontend sends `history` in the request body. This history is not validated beyond being a list. A malicious client could send a fabricated history to manipulate the AI expert's responses. This is a social-engineering surface, not a data integrity issue.

**Mitigating factor:** The Expert Room always creates a `conversation_id` on recommendation, so stateless mode is used only as a fallback.

---

## 11. Prioritized Improvement Roadmap

### P0 — Immediate / Before First Git Push or Sharing

| # | Issue | Action | Files |
|---|---|---|---|
| P0-1 | **Live API keys in `.env`** | Rotate all three API keys; confirm `.env` stays gitignored | `backend/.env`, `.gitignore` |

### P1 — High Priority (Security / Reliability)

| # | Issue | Action | Files |
|---|---|---|---|
| P1-1 | Panel endpoints have no auth | Add `auth.require_owner(_owner())` to `_panel_request()` | `backend/app.py` |
| P1-2 | `/knowledge` has no rate limit | Add `_ai_rate_limited()` | `backend/app.py` |
| P1-3 | Ollama never triggers cooldown | Fix `ollama_provider.py` to raise typed `ProviderError` | `backend/providers/ollama_provider.py` |
| P1-4 | Gemini errors wrapped into plain Exception | Remove outer exception wrapper in `gemini_provider.py` | `backend/providers/gemini_provider.py` |
| P1-5 | CORS wildcard | Restrict to known origin(s) | `backend/app.py` |
| P1-6 | requirements.txt bloat (torch/whisper/fastapi) | Trim to actual deps; saves ~3GB install | `backend/requirements.txt` |

### P2 — Medium Priority (Reliability / Performance)

| # | Issue | Action | Files |
|---|---|---|---|
| P2-1 | Purge called on every write | Move purge to background thread at startup | `backend/services/consultations.py`, `conversations.py` |
| P2-2 | Conversations list uses correlated subquery | Replace with JOIN + GROUP BY | `backend/services/conversations.py` |
| P2-3 | Gemini has no streaming | Implement streaming in `gemini_provider.py` | `backend/providers/gemini_provider.py` |
| P2-4 | `platform_stats()` loads all consultation rows | Add aggregation in SQL instead of Python loop | `backend/services/consultations.py` |
| P2-5 | `knowledge_service.py` parse errors silently dropped | Add logging | `backend/services/knowledge_service.py` |
| P2-6 | Debug mode always enabled | Read from env var `FLASK_DEBUG` | `backend/app.py` |

### P3 — Low Priority / Future Improvements

| # | Issue | Action | Files |
|---|---|---|---|
| P3-1 | Rate limiters in-memory only | Redis-backed rate limiting for multi-process deployment | `backend/app.py` |
| P3-2 | Live room close busy-polls DB | Background task + polling endpoint | `backend/services/live_engine.py` |
| P3-3 | Panel executor created per call | Module-level executor in `panel_engine.py` | `backend/services/panel_engine.py` |
| P3-4 | React `key={i}` in message lists | Use message content hash or position-stable ID | `frontend/src/components/ExpertRoom/ExpertChat.jsx` |
| P3-5 | `tempfile.mktemp()` deprecated | Use `tempfile.NamedTemporaryFile` pattern | `backend/tests/_testenv.py` |
| P3-6 | Extracted text fetched in full per reply | Limit SELECT or truncate at storage time | `backend/services/files.py` |
| P3-7 | `router.py` extra AI call per message | Evaluate if AI router adds value over keyword matching | `backend/services/router.py` |

---

## 12. Changes Safe to Implement Independently

These changes are low-risk, preserve all existing behavior, and do not require product approval:

1. **`ollama_provider.py` — Raise `ProviderError` for classified failures** (P1-3)
   - Replace the outer `except Exception as e: raise Exception(f"Ollama Provider Error: {e}")` with targeted exception catches that raise `ProviderError(category, detail)`. No behavior change for successful calls.

2. **`gemini_provider.py` — Remove exception wrapping** (P1-4)
   - Remove the `except Exception as e: raise Exception(f"Gemini Provider Error: {e}")` wrapper. SDK exceptions will propagate to `classify_exception()`, which handles them correctly. No behavior change on success.

3. **`knowledge_service.py` — Add parse error logging** (P2-5)
   - Add `print(f"[Knowledge] Parse error: {exc}\n{text}")` in the except block. No behavior change.

4. **`app.py` — Add `_ai_rate_limited()` to `/knowledge`** (P1-2)
   - One-line addition, consistent with other AI endpoints.

5. **`app.py` — Debug mode from env var** (P2-6)
   - Change `app.run(debug=True, ...)` to `app.run(debug=os.getenv("FLASK_DEBUG", "false") == "true", ...)`.

6. **`_testenv.py` — Replace `tempfile.mktemp()`** (P3-5)
   - `path = os.path.join(_tmpdir, f"test-{os.getpid()}.db")` or similar.

7. **`app.py` — Add `auth.require_owner` to panel** (P1-1)
   - Add `owner = auth.require_owner(_owner())` inside `_panel_request()`. Requires the frontend to already send `X-Client-Id` — which it does (confirmed in `api.js:headers()`).

8. **`requirements.txt` — Remove unused packages** (P1-6)
   - After verifying no import references: remove fastapi, uvicorn, starlette, whisper, openai-whisper, torch, transformers, tokenizers, huggingface-hub, google-cloud-dialogflow, google-genai, tiktoken, numba, llvmlite, SQLAlchemy, PyMySQL, greenlet.

---

## 13. Changes Requiring Owner Approval

These changes touch the product behavior, UI, security model, or infrastructure and must be explicitly approved before implementation:

1. **CORS origin restriction** (P1-5)
   - Requires confirming the exact production domain(s) before restricting.

2. **Session token migration to HttpOnly cookies** (6.9)
   - Changes authentication flow. Requires frontend and backend changes.

3. **Redis-backed rate limiting** (P3-1)
   - Requires infrastructure addition (Redis). Only needed for multi-process deployment.

4. **API key rotation** (P0-1)
   - Requires rotating keys at provider dashboards. Immediate action recommended.

5. **Background purge / scheduled jobs** (P2-1)
   - Changes when retention is applied; could affect data visibility timing.

6. **Live room close → async + polling** (P3-2)
   - Changes the client-server contract for the "End & Summarize" flow; requires frontend changes.

7. **AI router removal or replacement** (P3-7)
   - Would change which expert answers in Start Consultation chats; requires regression testing.

8. **Gemini streaming** (P2-3)
   - Changes user experience for streaming replies when Gemini is the active provider. Needs UI testing.

---

## Appendix: Positive Engineering Observations

The following patterns are well-engineered and should be preserved:

- **Atomic message storage** (`conversations.add_messages()`): user + reply saved together prevents orphaned messages
- **Provider failure isolation**: raw errors never reach the browser; `classify_exception()` maps everything to safe user messages  
- **Token/context budget management** (`services/context.py`): sophisticated graceful degradation for long conversations
- **Live room cross-process lock** (`busy_since` DB column): correct approach for multi-process coordination
- **Expert identity isolation in prompts** (`build_chat_prompt()`): explicit persona injection prevents expertise bleed
- **Expert switch does not change room** (`expert_key` vs `active_expert`): critical UX invariant correctly preserved
- **idempotency key for live messages** (`client_message_id UNIQUE`): prevents duplicate messages from retries
- **Test coverage**: `test_switching.py` and `test_provider_fallback.py` cover the two most complex subsystems with comprehensive scenarios
- **`hmac.compare_digest()` for token comparison**: timing-safe comparison prevents timing oracle attacks
- **Zero consultation content in metrics tables**: `operations`/`ai_calls` store only timings, categories, and identifiers
- **`_safe_display_name()`**: sanitizes uploaded filenames before storage
- **WAL journal mode**: SQLite WAL allows concurrent reads during writes, appropriate for the multi-threaded Flask server

---

*This audit was performed by read-only inspection of all source files. No files were modified.*
