-- ExpertOS initial schema.
-- Applied automatically by services/db.py (tracked in schema_migrations).

-- A consultation is counted as completed when ExpertOS successfully delivers
-- its main result: an Expert Room recommendation report, a Start Consultation
-- analysis, or an Expert Panel run with at least one successful expert.
-- Failed or abandoned attempts never create a row.
CREATE TABLE consultations (
    id                  TEXT PRIMARY KEY,          -- random UUID
    kind                TEXT NOT NULL CHECK (kind IN ('expert_room', 'quick_consultation', 'panel')),
    expert_keys         TEXT NOT NULL,             -- JSON list of backend expert keys
    status              TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed')),
    token_hash          TEXT NOT NULL,             -- SHA-256 of the access token; token itself is never stored
    problem             TEXT,                      -- only kept where a later feature needs it (panel → live room)
    result_json         TEXT,                      -- panel results used as live-room context
    created_at          TEXT NOT NULL,
    content_deleted_at  TEXT                       -- set when content is purged (retention or user request)
);

CREATE INDEX idx_consultations_status_created ON consultations (status, created_at);

-- One rating per consultation; repeat submissions are rejected.
CREATE TABLE ratings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    consultation_id  TEXT NOT NULL UNIQUE REFERENCES consultations (id) ON DELETE CASCADE,
    stars            INTEGER NOT NULL CHECK (stars BETWEEN 1 AND 5),
    feedback         TEXT,
    created_at       TEXT NOT NULL
);

-- User-facing operations (one per API request that calls the AI).
CREATE TABLE operations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_type    TEXT NOT NULL,
    expert_key      TEXT,
    started_at      TEXT NOT NULL,
    first_token_ms  INTEGER,
    total_ms        INTEGER NOT NULL,
    success         INTEGER NOT NULL CHECK (success IN (0, 1)),
    error_category  TEXT,
    timed_out       INTEGER NOT NULL DEFAULT 0 CHECK (timed_out IN (0, 1))
);

CREATE INDEX idx_operations_type_started ON operations (request_type, started_at);

-- Individual AI provider calls (several may serve one operation).
CREATE TABLE ai_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_type    TEXT NOT NULL,
    expert_key      TEXT,
    provider        TEXT,
    model           TEXT,
    started_at      TEXT NOT NULL,
    first_token_ms  INTEGER,
    total_ms        INTEGER NOT NULL,
    success         INTEGER NOT NULL CHECK (success IN (0, 1)),
    error_category  TEXT,
    attempts        INTEGER NOT NULL DEFAULT 1,
    timed_out       INTEGER NOT NULL DEFAULT 0 CHECK (timed_out IN (0, 1)),
    streamed        INTEGER NOT NULL DEFAULT 0 CHECK (streamed IN (0, 1))
);

CREATE INDEX idx_ai_calls_type_started ON ai_calls (request_type, started_at);

-- Live multi-expert consultation rooms (opened from a panel consultation).
CREATE TABLE live_sessions (
    id               TEXT PRIMARY KEY,
    consultation_id  TEXT NOT NULL REFERENCES consultations (id) ON DELETE CASCADE,
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    stage            INTEGER NOT NULL DEFAULT 0,   -- index into the discussion agenda
    rounds           INTEGER NOT NULL DEFAULT 0,
    busy_since       TEXT,                         -- set while a round is generating (cross-request lock)
    summary_json     TEXT,
    summary_error    TEXT,
    created_at       TEXT NOT NULL,
    closed_at        TEXT
);

CREATE INDEX idx_live_sessions_consultation ON live_sessions (consultation_id);

CREATE TABLE live_messages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES live_sessions (id) ON DELETE CASCADE,
    seq                INTEGER NOT NULL,
    role               TEXT NOT NULL CHECK (role IN ('expert', 'client', 'system')),
    expert_key         TEXT,
    content            TEXT NOT NULL,
    client_message_id  TEXT,                        -- idempotency key for client messages
    created_at         TEXT NOT NULL,
    UNIQUE (session_id, seq),
    UNIQUE (session_id, client_message_id)
);

-- Contact form submissions, reviewed by the site operator.
CREATE TABLE contact_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT,
    email       TEXT NOT NULL,
    subject     TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
