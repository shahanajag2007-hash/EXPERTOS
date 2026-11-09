"""
Accounts, sign-in sessions and request ownership.

Passwords are hashed with Werkzeug's scrypt-based hasher; session tokens and
client IDs are random secrets of which only SHA-256 hashes are stored.

Every request has an Owner:
- a signed-in user (Authorization: Bearer <session token>), and/or
- a browser (X-Client-Id: random ID the frontend generates once).
Conversations and files belong to the user when there is one, otherwise to
the browser. Signing in or registering claims the browser's anonymous
conversations and files for the account.
"""
import hashlib
import hmac
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from services import db
from services.consultations import Conflict, Forbidden, InvalidInput

SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")

# Compared against when an email is unknown, so a failed sign-in takes the
# same time whether or not the account exists.
_DUMMY_HASH = generate_password_hash("expertos-unused-password")


class Unauthorized(Exception):
    status_code = 401


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Owner:
    user_id: str | None
    client_hash: str | None

    @property
    def known(self):
        return bool(self.user_id or self.client_hash)

    def owns(self, row):
        """True if a conversation/file row belongs to this owner."""
        if row["user_id"]:
            return bool(self.user_id) and hmac.compare_digest(row["user_id"], self.user_id)
        return bool(self.client_hash and row["client_hash"]) and hmac.compare_digest(
            row["client_hash"], self.client_hash
        )

    def columns(self):
        """(user_id, client_hash) to store on a new row."""
        return self.user_id, self.client_hash


def _public_user(row):
    return {"id": row["id"], "email": row["email"], "name": row["name"] or ""}


def user_for_session(token):
    """The user row for a valid, unexpired session token, else None."""
    if not token:
        return None
    with db.connection() as conn:
        row = conn.execute(
            "SELECT u.* FROM auth_sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = ? AND s.expires_at > ?",
            (_sha256(token), db.utc_now()),
        ).fetchone()
    return row


def resolve_owner(session_token, client_id):
    """
    The Owner of a request. An invalid or expired session token raises
    Unauthorized (so the browser can sign the user out) rather than silently
    falling back to anonymous access.
    """
    user_id = None
    if session_token:
        user = user_for_session(session_token)
        if user is None:
            raise Unauthorized("Your session has expired. Please sign in again.")
        user_id = user["id"]

    client_hash = _sha256(client_id) if client_id and CLIENT_ID_RE.match(client_id) else None
    return Owner(user_id, client_hash)


def _validate_credentials(email, password):
    email = (email or "").strip().lower()
    errors = {}
    if not EMAIL_RE.match(email) or len(email) > 254:
        errors["email"] = "Please enter a valid email address."
    if not isinstance(password, str) or not password:
        errors["password"] = "Please enter your password."
    return email, errors


def _start_session(conn, user_id):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_sha256(token), user_id, now.isoformat(), (now + timedelta(days=SESSION_DAYS)).isoformat()),
    )
    conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now.isoformat(),))
    return token


def _claim_browser_data(conn, user_id, client_hash):
    """Attach the browser's anonymous conversations and files to the account."""
    if not client_hash:
        return
    for table in ("conversations", "uploaded_files"):
        conn.execute(
            f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL AND client_hash = ?",
            (user_id, client_hash),
        )


def register(email, password, name, owner):
    email, errors = _validate_credentials(email, password)
    name = (name or "").strip()
    if isinstance(password, str) and password and not (
        PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH
    ):
        errors["password"] = f"Use a password of {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters."
    if len(name) > 100:
        errors["name"] = "Name must be 100 characters or fewer."
    if errors:
        error = InvalidInput("Please correct the highlighted fields.")
        error.fields = errors
        raise error

    user_id = str(uuid.uuid4())
    with db.connection(write=True) as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise Conflict("An account with this email already exists. Sign in instead.")
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at, last_login_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email, name or None, generate_password_hash(password), db.utc_now(), db.utc_now()),
        )
        token = _start_session(conn, user_id)
        _claim_browser_data(conn, user_id, owner.client_hash)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"user": _public_user(row), "token": token}


def login(email, password, owner):
    email, errors = _validate_credentials(email, password)
    if errors:
        error = InvalidInput("Please correct the highlighted fields.")
        error.fields = errors
        raise error

    with db.connection(write=True) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        valid = check_password_hash(row["password_hash"] if row else _DUMMY_HASH, password)
        if row is None or not valid:
            raise Unauthorized("The email or password is incorrect.")
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (db.utc_now(), row["id"]))
        token = _start_session(conn, row["id"])
        _claim_browser_data(conn, row["id"], owner.client_hash)

    return {"user": _public_user(row), "token": token}


def logout(session_token):
    if not session_token:
        return
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_sha256(session_token),))


def current_user(session_token):
    row = user_for_session(session_token)
    if row is None:
        raise Unauthorized("You are not signed in.")
    return _public_user(row)


def require_owner(owner):
    if not owner.known:
        raise Forbidden("This browser could not be identified. Reload the page and try again.")
    return owner
