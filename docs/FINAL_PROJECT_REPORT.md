# ExpertOS — Final Project Report
## Build On AWS Challenge 2026

## 1. Project Overview

ExpertOS is an AI-powered technical consultation platform that provides access to six specialised AI experts across software engineering domains. Users can consult individual experts, run multi-expert panels, host live group discussions, and upload documents for expert analysis. Conversations are saved and searchable, reports are downloadable, and accounts are optional.

The project was built and refined using **Kiro**, an AI-powered development environment, as the primary development tool throughout the project lifecycle.

## 2. Key Features

| Feature | Description |
|---|---|
| **Expert Rooms** | Six specialised AI experts (Frontend, Backend, Mobile, DevOps, Security, AI/ML) with distinct personalities and deep domain knowledge |
| **Expert Panel** | Multi-expert consultation: all six experts analyse a problem in parallel and deliver a consolidated recommendation |
| **Live Discussion Room** | Real-time moderated discussion where experts work through a five-item agenda, then answer user questions |
| **Start Consultation** | Guided consultation flow that routes questions to the most relevant expert |
| **Knowledge Explorer** | Cross-domain knowledge search and exploration |
| **Design Advisor** | Architecture and system design consultation |
| **File Uploads** | PDF, Word, Excel, PowerPoint, ZIP, images, and code files; text is extracted for expert context |
| **Conversation History** | Conversations are saved and can be reopened; accounts persist history across devices |
| **Streaming Responses** | Real-time token streaming from AI providers |
| **AI Provider Fallback** | Four-provider chain: OpenRouter → Gemini → Groq → Ollama |
| **Download Reports** | Expert recommendations and live discussion summaries download as Markdown |

## 3. Technology Stack

### Frontend
- React 19 + Vite
- Tailwind CSS 4
- Vitest + Testing Library

### Backend
- Python 3.12 + Flask
- SQLite (with WAL mode for concurrent reads)
- pypdf, python-docx equivalents, openpyxl for document extraction

### AI Providers
- **OpenRouter** (primary) — access to a wide range of models via a single API; configurable model list
- **Google Gemini** (fallback)
- **Groq** (fallback)
- **Ollama** (local fallback)

### AWS Integration
- **Amazon S3** — document storage backend (boto3 1.38.23)
- SSE-S3 encryption, private access, IAM role credential chain

### Development
- **Kiro IDE** — AI-powered development environment used throughout
- pytest (228 automated tests)
- GitHub for version control

## 4. AWS Integration

ExpertOS integrates **Amazon S3** as a pluggable document storage backend.

### How it works

When users upload documents (PDF, Word, code files, etc.), ExpertOS:
1. Validates the file type and size
2. Extracts text for expert context
3. Stores the file under a random UUID hex key (not the original filename)
4. Serves the file only to its owner via the backend — never directly from S3

### Key design decisions

- **Privacy**: all S3 objects are private. No public bucket policy.
- **Encryption**: every `PutObject` call specifies `ServerSideEncryption=AES256` (SSE-S3, free).
- **No vendor lock-in**: `STORAGE_BACKEND=local` (the default) uses local filesystem — S3 is optional.
- **IAM role support**: boto3's standard credential chain means production deployments on EC2 or Elastic Beanstalk work without any access keys in the environment.
- **No silent failures**: S3 errors are reported to the user. The application never silently falls back to local storage when S3 is configured.
- **No credential exposure**: AWS credentials are read by the backend only, never sent to the browser or logged.

### Configuration

```env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=expertos-uploads-YOURSUFFIX
AWS_REGION=ap-south-1
```

See `docs/AWS_SETUP.md` for full setup instructions.

## 5. Kiro's Role in Development

Kiro was used as the primary development tool throughout the project:

- **Technical audit**: Kiro conducted a comprehensive review of the codebase, identifying security issues, incomplete features, and improvement opportunities
- **Implementation**: AI provider fallback chain, conversation persistence, context management, and file handling were implemented or improved with Kiro
- **S3 integration**: `backend/services/storage.py` was designed and implemented with Kiro, including the factory pattern, error handling, and credential chain
- **Testing**: the full test suite (228 tests) was written and verified with Kiro
- **Documentation**: all technical documentation, deployment guides, and this report were prepared with Kiro
- **Security review**: Kiro identified and addressed security issues including authentication hardening, input validation, rate limiting, and credential handling

## 6. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (React SPA)                       │
│  Expert Rooms │ Panel │ Live Room │ Consultation │ Explorer  │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / SSE streaming
┌───────────────────────────▼─────────────────────────────────┐
│                   Flask Backend (Python)                      │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  Auth/Users │  │  Experts/AI  │  │  Files/Storage   │   │
│  └──────┬──────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                │                    │              │
│  ┌──────▼──────────────────────────┐  ┌──────▼──────────┐  │
│  │         SQLite Database          │  │  LocalStorage   │  │
│  │  (users, conversations, files,   │  │       OR        │  │
│  │   sessions, live rooms, metrics) │  │   Amazon S3     │  │
│  └──────────────────────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┬──────────┐
            ▼               ▼               ▼          ▼
       OpenRouter       Gemini API       Groq API    Ollama
      (primary)        (fallback 1)    (fallback 2) (fallback 3)
```

## 7. Security

| Area | Implementation |
|---|---|
| Passwords | Werkzeug scrypt hashes — no plaintext storage |
| Session tokens | SHA-256 hashes only in the database |
| API credentials | Backend-only — never sent to browser or logged |
| File access | Owner-checked on every request; random storage keys |
| S3 objects | Private, SSE-S3 encrypted |
| Rate limiting | Per-IP limits on AI requests, uploads, sign-in, contact form |
| Input validation | File type checked from content bytes, not just extension |
| Upload size | Configurable limit (default 10 MB per file) |
| CORS | Currently wildcard; production deployment should restrict to frontend domain |

## 8. AI Infrastructure

ExpertOS uses a four-provider fallback chain:

1. **OpenRouter** (primary) — access to many models via a single API; configurable model list
2. **Gemini** — Google's API as first fallback
3. **Groq** — fast inference as second fallback
4. **Ollama** — local model as final fallback (no external dependency)

Each provider is tried once per request. A provider that returns a usage-limit or authentication error is paused until its reset time, preventing repeated failed calls. All four providers support streaming responses.

Each of the six expert identities has a distinct system prompt that defines personality, domain focus, and communication style. These are isolated per conversation — an expert in one room never sees the context from another.

## 9. Testing

**228 automated tests, 0 failures.**

| Test area | Count | Notes |
|---|---|---|
| API endpoints | ~60 | Full HTTP request/response cycle |
| AI provider fallback | ~30 | Mock providers, fallback ordering |
| Conversation persistence | ~25 | Save, load, isolation, account migration |
| S3 storage | 31 | All mocked — no real AWS credentials required |
| Intent detection | ~20 | Social vs. technical message classification |
| Live discussion engine | ~20 | Phase transitions, agenda, speaker rotation |
| File processing | ~20 | Upload, extract, delete, authorization |
| Expert routing | ~15 | Correct expert selection |
| OpenRouter routing | ~7 | Model selection, vision routing |

All S3 tests use `unittest.mock.patch` to mock `boto3.client`. The full test suite runs without any AWS account or credentials.

## 10. Running Locally

```powershell
# 1. Clone the repository
git clone https://github.com/shahanajag2007-hash/EXPERTOS.git
cd EXPERTOS

# 2. Backend
cd backend
pip install -r requirements.txt
copy .env.example .env
# Edit .env: add OPENROUTER_API_KEY
python app.py

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The application runs fully locally without any AWS configuration.

## 11. Known Limitations

- No password reset or email verification.
- Scanned (image-only) PDFs are not OCR'd — upload screenshots of pages instead.
- Expert Panel and Live Room do not support file uploads.
- Rate limits are in-memory — single backend process only (or move to Redis for scale-out).
- When `STORAGE_BACKEND=s3`, S3 failures return an error to the user (no silent fallback).
- Existing locally-stored files are not migrated when switching to S3.
- CORS is currently wildcard — restrict to your frontend domain in production.

## 12. Competition Relevance

This project demonstrates meaningful AWS S3 integration:

- **Real integration**: files are actually stored in S3 when configured — not simulated
- **Production-ready**: private objects, SSE-S3 encryption, IAM role support
- **Well-tested**: 31 unit tests specifically for the S3 storage layer
- **Documented**: full setup guide, integration report, and deployment guide
- **Optional**: the application works fully without AWS (local storage default), making it accessible to evaluators without AWS access

Amazon S3 was chosen because it is the natural fit for the existing file storage need: it solves a real problem (persistent, scalable document storage) without introducing unnecessary services or changing the application's architecture.
