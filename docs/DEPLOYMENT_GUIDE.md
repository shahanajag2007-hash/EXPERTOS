# Deployment Guide

This guide covers running ExpertOS in production. The application is a Flask API backend with a React SPA frontend.

## Architecture

```
Browser
  │
  ├── Static files (React SPA)  ←  Render Static Site  (or nginx / S3+CloudFront)
  │
  └── API requests  →  Flask backend on Render Web Service (gunicorn, port $PORT)
                            │
                            ├── SQLite database  (/data/expertos.db  — persistent disk)
                            ├── Local file storage  (/data/uploads/)  OR
                            └── Amazon S3  (when STORAGE_BACKEND=s3)
```

---

## Recommended: Deploy on Render (Fastest Path)

ExpertOS includes a `render.yaml` blueprint at the project root. Render reads this file and automatically creates both services (backend Web Service + frontend Static Site) from your GitHub repository.

### Step-by-step

1. **Push to GitHub** (already done):
   ```
   git push origin main
   ```

2. **Create a Render account** at https://render.com (free tier available).

3. **New → Blueprint** → connect your GitHub repository (`shahanajag2007-hash/EXPERTOS`).

4. Render reads `render.yaml` and shows you two services to create:
   - `expertos-backend` — Python Web Service with a 1 GB persistent disk
   - `expertos-frontend` — Static Site

5. **Set secret environment variables** in the Render dashboard after services are created (these are marked `sync: false` in `render.yaml` — Render will prompt you):
   | Variable | Value |
   |---|---|
   | `OPENROUTER_API_KEY` | Your OpenRouter key |
   | `GEMINI_API_KEY` | Optional fallback |
   | `GROQ_API_KEY` | Optional fallback |
   | `S3_BUCKET_NAME` | Your bucket name (if using S3) |
   | `AWS_ACCESS_KEY_ID` | Your IAM access key (if using S3) |
   | `AWS_SECRET_ACCESS_KEY` | Your IAM secret key (if using S3) |

6. **Update the CORS and API URL** after the first deploy:
   - Note your actual backend URL (e.g. `https://expertos-backend-xxxx.onrender.com`)
   - In `render.yaml`, update `CORS_ORIGINS` and `VITE_API_URL` to match
   - Or set them in the Render dashboard directly
   - Commit and push to trigger a redeploy

7. **Frontend URL**: your static site will be at `https://expertos-frontend.onrender.com` (or with a suffix if the name is taken).

### Important Render free-tier notes

- **Spin-down**: Free Web Services spin down after 15 minutes of inactivity. The first request after spin-down takes ~30 seconds. Upgrade to a paid plan to keep it always-on.
- **Persistent disk**: The 1 GB disk (`/data`) costs ~$0.25/GB/month on paid plans. On the free plan, a persistent disk is not available — SQLite data will be lost on restart. **For a real deployment, use a paid plan or switch `STORAGE_BACKEND=s3` and accept that the SQLite DB resets on restart (consultation stats and accounts are lost, but AI features still work).**
- **Build minutes**: 400 free build minutes/month — sufficient for development.

### Free-tier workaround (SQLite without persistent disk)

If you want to demo ExpertOS on Render's free tier without paying for a disk:
- Set `EXPERTOS_DB_PATH` to `/tmp/expertos.db` (ephemeral — resets on restart)
- Set `EXPERTOS_UPLOAD_DIR` to `/tmp/uploads`
- Use `STORAGE_BACKEND=s3` for document storage (S3 is persistent)
- This means conversation history and accounts reset when the service restarts, but AI consultations, Expert Panel, and file uploads via S3 all work.

---

## Local Development

```powershell
# Terminal 1 — backend
cd backend
pip install -r requirements.txt
copy .env.example .env   # then edit .env with your API keys
python app.py            # http://127.0.0.1:5000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev              # http://localhost:5173
```

See README.md for full development setup.

## Frontend Build

```bash
cd frontend
npm run build
```

This produces `frontend/dist/` — a self-contained static site. Serve it from nginx, S3 + CloudFront, or any static file host. The `VITE_API_URL` environment variable must be set at build time.

## Backend Production Server

Gunicorn is included in `requirements.txt`. Start with a single worker:

```bash
cd backend
gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 --timeout 180 app:app
```

**Single worker is required**: SQLite WAL mode and the in-memory rate limiters are not safe across multiple workers.

For Windows, use waitress instead:
```powershell
pip install waitress
python -m waitress --port=5000 app:app
```

## Environment Variables

All required secrets and configuration go in `backend/.env` (or as environment variables in your deployment platform). See `backend/.env.example` for all supported variables.

Required for production:

| Variable | Value |
|---|---|
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `FLASK_DEBUG` | `false` |
| `CORS_ORIGINS` | Your frontend URL (e.g. `https://expertos-frontend.onrender.com`) |
| `STORAGE_BACKEND` | `local` or `s3` |
| `S3_BUCKET_NAME` | Your bucket name (if using S3) |
| `AWS_REGION` | `ap-south-1` or your region (if using S3) |

On EC2/Elastic Beanstalk with an IAM role, leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` unset.

## Database Persistence

SQLite database path is controlled by `EXPERTOS_DB_PATH` (default `backend/data/expertos.db`). It is created automatically on first start. In production:

- Mount the database directory on persistent storage (Render disk, EBS volume, Docker volume)
- Back up `expertos.db` regularly — it contains all conversations, accounts, and ratings
- To start fresh: stop the backend and delete the `.db`, `.db-shm`, and `.db-wal` files

## File Storage

**Local mode** (default): files are stored in `EXPERTOS_UPLOAD_DIR`. Mount this directory on persistent storage.

**S3 mode**: files are stored in S3. No local persistence needed for uploads. See [docs/AWS_SETUP.md](AWS_SETUP.md).

## CORS Configuration

Set `CORS_ORIGINS` to your frontend domain in production:

```
CORS_ORIGINS=https://expertos-frontend.onrender.com
```

For multiple origins, use a comma-separated list. Leave unset or `"*"` for local development.

## Health Check

```
GET /health
```

Returns HTTP 200 with a JSON body when the backend is healthy. Render uses `/health` as the health-check endpoint (configured in `render.yaml`).

## AWS Elastic Beanstalk / EC2 Quick Start

1. **Launch EC2 instance** (Amazon Linux 2023, t3.micro for demo)
2. **Install Python and gunicorn**:
   ```bash
   sudo dnf install python3.12 -y
   pip3 install -r requirements.txt
   ```
3. **Create IAM role** with the S3 policy (see [docs/AWS_SETUP.md](AWS_SETUP.md))
4. **Attach IAM role** to the EC2 instance
5. **Set environment variables** (via EB environment properties or a `.env` file)
6. **Start backend**: `bash render_start.sh` (or `gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 --timeout 180 app:app`)
7. **Build and serve frontend**: `npm run build` → upload `dist/` to S3 + CloudFront, or serve with nginx

## Security Checklist for Production

- [x] `FLASK_DEBUG=false` in production (set in render.yaml)
- [x] CORS restricted via `CORS_ORIGINS` env var
- [x] Secrets in environment variables, not in code
- [x] `USE_SYSTEM_CERTIFICATES=false` on Linux (not needed, standard CA bundle works)
- [ ] HTTPS enabled (Render provides HTTPS automatically on `.onrender.com` domains)
- [ ] IAM role used instead of access keys on EC2/EB
- [ ] S3 bucket has Block Public Access enabled
- [ ] Persistent disk or S3 configured for data durability
- [ ] Rate limiting active (defaults: 200 AI requests/hour/IP)
