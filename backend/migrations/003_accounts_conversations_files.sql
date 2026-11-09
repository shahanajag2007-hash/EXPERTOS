-- Accounts, saved conversations and uploaded files.
--
-- Ownership: every browser sends a random client ID (X-Client-Id); only its
-- SHA-256 hash is stored. A signed-in user's requests also carry a session
-- token. A conversation or file belongs to its user when user_id is set,
-- otherwise to the browser (client_hash). Signing in claims the browser's
-- anonymous conversations and files for the account.

CREATE TABLE users (
    id             TEXT PRIMARY KEY,            -- random UUID
    email          TEXT NOT NULL UNIQUE,        -- lower-cased
    name           TEXT,
    password_hash  TEXT NOT NULL,               -- werkzeug scrypt/pbkdf2 hash, never the password
    created_at     TEXT NOT NULL,
    last_login_at  TEXT
);

CREATE TABLE auth_sessions (
    token_hash     TEXT PRIMARY KEY,            -- SHA-256 of the session token
    user_id        TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at     TEXT NOT NULL,
    expires_at     TEXT NOT NULL
);

CREATE INDEX idx_auth_sessions_user ON auth_sessions (user_id);

-- Expert Room chats and Start Consultation sessions.
CREATE TABLE conversations (
    id               TEXT PRIMARY KEY,          -- random UUID
    kind             TEXT NOT NULL CHECK (kind IN ('expert_room', 'quick_consultation')),
    user_id          TEXT REFERENCES users (id) ON DELETE CASCADE,
    client_hash      TEXT,
    expert_key       TEXT NOT NULL,             -- expert the conversation started with
    active_expert    TEXT NOT NULL,             -- expert currently answering
    title            TEXT NOT NULL,
    project          TEXT NOT NULL DEFAULT '',
    answers_json     TEXT,                      -- Expert Room discovery answers
    report_json      TEXT,                      -- recommendation or analysis shown to the user
    consultation_id  TEXT REFERENCES consultations (id) ON DELETE SET NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE INDEX idx_conversations_user ON conversations (user_id, updated_at);
CREATE INDEX idx_conversations_client ON conversations (client_hash, updated_at);

CREATE TABLE conversation_messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'expert', 'system')),
    expert_key       TEXT,
    content          TEXT NOT NULL,
    file_ids         TEXT,                      -- JSON list of files attached to a user message
    created_at       TEXT NOT NULL
);

CREATE INDEX idx_conversation_messages_conv ON conversation_messages (conversation_id, id);

-- Uploaded files. The file itself is stored under backend/data/uploads with a
-- random name and is never served back; extracted_text is what the experts read.
CREATE TABLE uploaded_files (
    id               TEXT PRIMARY KEY,          -- random UUID
    user_id          TEXT REFERENCES users (id) ON DELETE CASCADE,
    client_hash      TEXT,
    conversation_id  TEXT REFERENCES conversations (id) ON DELETE SET NULL,
    filename         TEXT NOT NULL,             -- original name, for display only
    content_type     TEXT NOT NULL,
    size_bytes       INTEGER NOT NULL,
    kind             TEXT NOT NULL CHECK (kind IN ('document', 'image')),
    storage_name     TEXT NOT NULL,
    extracted_text   TEXT,
    extraction_note  TEXT,                      -- e.g. "first 40 of 120 pages", or why nothing was extracted
    created_at       TEXT NOT NULL
);

CREATE INDEX idx_uploaded_files_owner ON uploaded_files (user_id, client_hash);
CREATE INDEX idx_uploaded_files_conversation ON uploaded_files (conversation_id);
