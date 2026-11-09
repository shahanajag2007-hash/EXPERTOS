# ExpertOS

AI technical consultation platform: six specialised AI experts, Expert Room
recommendations, a multi-expert panel with a live discussion room, an AI
Guide, a Knowledge Explorer and a Design Advisor. Conversations are saved and
can be reopened, documents and screenshots can be uploaded for the experts to
read, reports can be downloaded, and accounts are optional.

- `frontend/`: React 19 + Vite + Tailwind CSS 4
- `backend/`: Flask API, SQLite persistence, AI provider routing (OpenRouter first, then Gemini, Groq and Ollama as fallbacks), Amazon S3 document storage (boto3)

## Requirements

- Python 3.12+
- Node.js 20+
- An OpenRouter API key (https://openrouter.ai/keys)

## Setup

```powershell
# Backend
cd backend
pip install -r requirements.txt
copy .env.example .env        # then add your OPENROUTER_API_KEY
python scripts/check_ai_providers.py   # checks HTTPS, key and models; prints no secrets

# Frontend
cd ..\frontend
npm install
```

## Run

Two terminals:

```powershell
cd backend
python app.py                 # http://127.0.0.1:5000
```

```powershell
cd frontend
npm run dev                   # http://localhost:5173
```

The frontend calls `http://127.0.0.1:5000` by default. Set `VITE_API_URL` in
`frontend/.env` to use another backend address.

## Configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Primary AI provider key (required for real consultations) |
| `OPENROUTER_MODELS` | Optional comma-separated model IDs, tried in order |
| `OPENROUTER_REASONING` | `off` (default), `low`, `medium` or `high` |
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_URL` | Optional fallback providers |
| `GROQ_MODEL` | Groq fallback model (default `openai/gpt-oss-120b`; list available IDs with `GET https://api.groq.com/openai/v1/models`) |
| `USE_SYSTEM_CERTIFICATES` | `true` (default): verify HTTPS against the OS trust store (needed behind antivirus HTTPS scanning or corporate proxies) |
| `EXPERTOS_DB_PATH` | Database file (default `backend/data/expertos.db`) |
| `CONTENT_RETENTION_DAYS` | Days before panel content and live transcripts are deleted (default 30) |
| `CONTACT_RETENTION_DAYS` | Days before contact messages are deleted (default 180) |
| `LIVE_TURNS_PER_ROUND` | Experts who speak per live-room agenda round (default 2) |
| `LIVE_STAGE_SPEAKERS` | Different experts who must contribute before an agenda item is complete, capped at the participants (default 3) |
| `LIVE_MAX_ROUNDS` | Client questions answered per live session; agenda rounds don't count (default 40) |
| `OPENROUTER_VISION_MODELS` | Optional comma-separated image-capable OpenRouter models, used when screenshots are attached |
| `AI_REQUESTS_PER_HOUR` | AI requests allowed per IP address per hour (default 200) |
| `UPLOAD_MAX_MB` | Maximum size of one uploaded file (default 10) |
| `EXPERTOS_UPLOAD_DIR` | Where uploaded files are stored (default `backend/data/uploads`) |
| `SESSION_DAYS` | How long a sign-in lasts (default 30) |
| `ANONYMOUS_CONVERSATION_RETENTION_DAYS` | Days of inactivity before conversations saved without an account are deleted (default 90) |

API keys stay on the backend and are never sent to the browser. `.env` and the
database file are git-ignored.

## Amazon S3 File Storage

By default, uploaded documents are stored locally in `backend/data/uploads/`. To store them in Amazon S3 instead, set `STORAGE_BACKEND=s3` and configure the required AWS variables (see [docs/AWS_SETUP.md](docs/AWS_SETUP.md)).

| Variable | Purpose |
|---|---|
| `STORAGE_BACKEND` | `local` (default) or `s3` |
| `S3_BUCKET_NAME` | S3 bucket name (required when `STORAGE_BACKEND=s3`) |
| `AWS_REGION` | AWS region (default `us-east-1`) |
| `AWS_ACCESS_KEY_ID` | Access key for local dev (leave empty to use IAM role) |
| `AWS_SECRET_ACCESS_KEY` | Secret key for local dev (leave empty to use IAM role) |

S3 objects are stored with SSE-S3 encryption and private access. AWS credentials are never sent to the browser or logged.

## Database

SQLite, created automatically on first start. Migrations are numbered SQL
files in `backend/migrations/`, applied in order once each and recorded in the
`schema_migrations` table. To start fresh, stop the backend and delete
`backend/data/expertos.db*`.

What is stored and for how long is described on the in-app Privacy page
(`frontend/src/pages/Privacy.jsx`). In short:

- **consultations**: one row per *completed* consultation, meaning a delivered
  Expert Room report, Start Consultation analysis, or panel run with at least
  one successful expert. Failed or abandoned attempts create no row. Access is
  by a random token returned once to the browser; only its SHA-256 hash is stored.
- **ratings**: one per consultation (1–5 stars, optional feedback).
- **operations / ai_calls**: response-time measurements (no consultation text).
- **live_sessions / live_messages**: live room transcripts and summaries.
- **contact_messages**: contact form submissions. Read them with
  `python scripts/list_contact_messages.py`.
- **users / auth_sessions**: optional accounts. Passwords are stored only as
  Werkzeug scrypt hashes; session tokens only as SHA-256 hashes.
- **conversations / conversation_messages**: saved Expert Room and Start
  Consultation conversations (answers or project, report, messages). Each
  belongs to an account, or without one to the browser's random client ID
  (only its hash is stored). Signing in moves the browser's conversations to
  the account. A user message is saved together with its answer, so a failed
  AI request never leaves a duplicate or unanswered question.
- **uploaded_files**: uploads and their extracted text. The files themselves
  are in `backend/data/uploads` under random names, are never served back, and
  are usable only by their owner. Deleting a conversation deletes its files.

## Conversations, context and uploads

- Each chat request is answered with the conversation's saved history: the
  latest 12 messages in full and earlier ones condensed within a size budget
  (`services/context.py`). The prompt states when earlier messages are left
  out, so nothing is dropped silently. Replies that hit the token limit are
  marked as cut off.
- Uploads (`POST /files`): PDF (via pypdf), Word .docx, Excel .xlsx,
  PowerPoint .pptx, ZIP (its text files), plain text, Markdown, CSV, JSON and
  code, plus PNG/JPEG/WebP/GIF images. Up to 5 files per request, 10 MB each.
  The type is checked from the content, not just the name. Old .doc/.xls/.ppt,
  password-protected and unsupported files are rejected with the reason.
  Scanned PDFs without selectable text are accepted but flagged as having no
  text.
- Documents are included in the expert's prompt (up to 40,000 characters,
  shared between files; anything cut is stated). Images are sent only to
  image-capable models (OpenRouter vision models and Gemini); Groq and Ollama
  are skipped for those requests.
- Reports (Expert Room recommendation, Start Consultation analysis, live
  discussion summary) download as Markdown built from the real answers,
  report, discussion and attached file names.

## Statistics and measurement rules

`GET /stats` (homepage) and `GET /stats/performance` are computed from stored
records only; they never call an AI provider.

- **Consultations completed**: count of consultation rows (see above).
- **Satisfaction rate**: ratings of 4 or 5 stars ÷ all ratings × 100. Shows
  "Awaiting first ratings" when there are none.
- **Average response**: mean backend-measured time of successful single-expert
  requests (recommendations, Expert Room chat, Start Consultation analysis and
  follow-ups) over the last 30 days. Panel runs are reported separately.
  Shows "Measuring response times" until a request has completed.
- `/stats/performance` adds median, p95, success, timeout and within-30s rates
  per request type, per expert and per model, plus time to first streamed token.

## Live Expert Discussion Room

The backend (`services/live_engine.py`) controls the phases and enforces them:

1. **Expert discussion**: on entering, the experts work through the five
   agenda items in order; the page requests agenda rounds automatically. An
   item is complete only when enough different experts have contributed to it
   (failed turns don't count). The message box is locked, and the API rejects
   client messages in this phase.
2. **User interaction**: after the last item the box unlocks with "You can
   discuss your queries and interact with the experts now." The addressed or
   most relevant expert(s) answer; greetings get one brief reply
   (`services/intent.py`).
3. **End & Summarize**: no new turns start; a turn being written finishes and
   is saved; the room becomes "Key Takeaways from the Live Discussion",
   generated only from the transcript. If the agenda wasn't finished, the
   takeaways say so. The transcript and takeaways remain after a refresh.

## Message intent

Short social messages (greetings, small talk, thanks, acknowledgements,
goodbyes) are recognised in `services/intent.py`. They are answered by the
current expert in a sentence or two, without expert routing or hand-over. A
greeting that comes with a request ("hi, can you review my schema?") is
treated as a request. The replies are still written by the AI.

## AI provider fallback

Requests go to OpenRouter, then Gemini, Groq and Ollama, each tried at most
once per request. A response is accepted only if it is non-empty and not cut
off. When a provider reports a usage limit, a rejected key, a missing model or
is unreachable, the backend pauses it (until its reported quota reset when
available) instead of calling it on every request; if every provider is
paused, requests fail immediately with the reason and the expected reset time.
Each attempt is recorded in `ai_calls.provider_attempts`.

## Tests

```powershell
cd backend
python -m unittest discover -s tests -v    # AI providers mocked; uses a temporary database

cd ..\frontend
npm test          # Vitest + Testing Library (jsdom)
npm run lint
npm run build
```

`python scripts/check_ai_providers.py --live` makes one real AI request; it is
the only check that uses your API quota.

## Known limitations

- No password reset or email verification (there is no email service).
  Without an account, conversations are tied to the browser; clearing its
  site data loses access to them.
- Scanned (image-only) PDFs are not OCR'd; send screenshots of the pages
  instead, which image-capable models can read.
- Expert Panel and the live room don't take file uploads.
- OpenRouter free models have a daily request limit per account; when it is
  reached the app reports a usage-limit error and falls back to other providers
  if configured.
- Rate limits (ratings, contact, sign-in, uploads, AI requests) are kept in
  memory per process. Run a single backend process, or move them to a shared
  store, before scaling out.
- When `STORAGE_BACKEND=s3`, S3 upload failures return an error to the user rather than silently falling back to local storage.
- Existing locally-stored files are not migrated when switching to S3. They remain accessible only from the local filesystem.
