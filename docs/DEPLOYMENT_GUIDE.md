# Deployment Guide

This guide covers running ExpertOS in production. The application is a Flask API backend with a React SPA frontend.

## Architecture

```
Browser
  │
  ├── Static files (React SPA)  ←  served by nginx / S3+CloudFront / same Flask process
  │
  └── API requests  →  Flask backend (port 5000)
                            │
                            ├── SQLite database  (backend/data/expertos.db)
                            ├── Local file storage  (backend/data/uploads/)  OR
                            └── Amazon S3  (when STORAGE_BACKEND=s3)
```

## Requirements

- Python 3.12+
- Node.js 20+ (build time only)
- A process manager: gunicorn (Linux/Mac) or waitress (Windows)
- nginx or a CDN to serve the built frontend (or Flask can serve it in single-process mode)

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

This produces `frontend/dist/` — a self-contained static site. Serve it from nginx, S3 + CloudFront, or any static file host.

## Backend Production Server

Install gunicorn:
```bash
pip install gunicorn
```

Start with a single worker (required for SQLite WAL-mode compatibility — multiple workers share one write connection via WAL, but a single gunicorn worker is simplest and sufficient for most deployments):

```bash
cd backend
gunicorn -w 1 -b 0.0.0.0:5000 app:app
```

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
| `STORAGE_BACKEND` | `local` or `s3` |
| `S3_BUCKET_NAME` | Your bucket name (if using S3) |
| `AWS_REGION` | `ap-south-1` or your region (if using S3) |

On EC2/Elastic Beanstalk with an IAM role, leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` unset.

## Database Persistence

SQLite database is at `backend/data/expertos.db`. It is created automatically on first start. In production:

- Mount `backend/data/` on persistent storage (EBS volume, Docker volume, etc.)
- Back up `expertos.db` regularly — it contains all conversations, accounts, and ratings
- To start fresh: stop the backend and delete `backend/data/expertos.db*` (WAL and SHM files too)

## File Storage

**Local mode** (default): files are stored in `backend/data/uploads/`. Mount this directory on persistent storage.

**S3 mode**: files are stored in S3. No local persistence needed for uploads. See [docs/AWS_SETUP.md](AWS_SETUP.md).

## CORS Configuration

The backend currently allows all origins (`*`). For production, restrict this to your frontend domain. Set the `CORS_ORIGINS` environment variable (or hardcode it in `app.py` if the variable is not yet wired up).

**Note**: CORS restriction is a planned security improvement for production deployment.

## Health Check

```
GET /health
```

Returns HTTP 200 with a JSON body when the backend is healthy. Use this as the health-check endpoint for load balancers and deployment platforms.

## AWS Elastic Beanstalk / EC2 Quick Start

This is the recommended AWS deployment path for the Build On AWS Challenge:

1. **Launch EC2 instance** (Amazon Linux 2023, t3.micro for demo)
2. **Install Python and gunicorn**:
   ```bash
   sudo dnf install python3.12 -y
   pip3 install -r requirements.txt gunicorn
   ```
3. **Create IAM role** with the S3 policy (see [docs/AWS_SETUP.md](AWS_SETUP.md))
4. **Attach IAM role** to the EC2 instance
5. **Set environment variables** (via EB environment properties or a `.env` file)
6. **Start backend**: `gunicorn -w 1 -b 0.0.0.0:5000 app:app`
7. **Build and upload frontend**: `npm run build` → upload `dist/` to S3 + CloudFront, or serve with nginx from the same instance

Alternatively, use **AWS Elastic Beanstalk** with a Python platform — it handles deployment, scaling, and health monitoring automatically.

## Security Checklist for Production

- [ ] `FLASK_DEBUG=false` in production
- [ ] HTTPS enabled (via nginx reverse proxy or load balancer)
- [ ] CORS restricted to your frontend domain
- [ ] `OPENROUTER_API_KEY` and other secrets in environment variables, not in code
- [ ] IAM role used instead of access keys on EC2/EB
- [ ] S3 bucket has Block Public Access enabled
- [ ] `backend/data/` is on persistent storage and backed up
- [ ] Rate limiting is configured (defaults: 200 AI requests/hour/IP)
- [ ] No debug output in production logs
