#!/usr/bin/env bash
# Render startup script for the ExpertOS backend.
# This runs before gunicorn starts and ensures the persistent disk is ready.
set -e

# Ensure the persistent disk directories exist.
# EXPERTOS_DB_PATH and EXPERTOS_UPLOAD_DIR are set by render.yaml.
DB_DIR=$(dirname "${EXPERTOS_DB_PATH:-/tmp/expertos-data/expertos.db}")
UPLOAD_DIR="${EXPERTOS_UPLOAD_DIR:-/tmp/expertos-data/uploads}"

mkdir -p "$DB_DIR"
mkdir -p "$UPLOAD_DIR"

echo "[render_start] Data directory: $DB_DIR"
echo "[render_start] Upload directory: $UPLOAD_DIR"
echo "[render_start] Starting gunicorn..."

# Single worker — required for SQLite WAL mode and in-memory rate limiters.
# --threads 4 allows concurrent requests within one worker.
# --timeout 180 covers long AI streaming responses (default is 30s, too short).
# --keep-alive 5 keeps connections open for SSE streams.
exec gunicorn \
  -w 1 \
  --threads 4 \
  -b "0.0.0.0:${PORT:-5000}" \
  --timeout 180 \
  --keep-alive 5 \
  --access-logfile - \
  --error-logfile - \
  app:app
