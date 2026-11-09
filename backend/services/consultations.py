"""
Consultation records, access tokens, ratings, retention and statistics.

Access model: there are no user accounts. Each completed consultation gets a
random ID and a separate random access token that is returned once to the
browser that ran it. Only the token's SHA-256 hash is stored. Reading or
changing anything tied to a consultation (rating it, the live room, deleting
its content) requires the token; knowing the ID alone is not enough.
"""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from services import db
from services.expert_manager import expert_manager

# Problem descriptions and transcripts are deleted after this many days.
# Counts, timings and ratings (which contain no project content) are kept.
CONTENT_RETENTION_DAYS = int(os.getenv("CONTENT_RETENTION_DAYS", "30"))
CONTACT_RETENTION_DAYS = int(os.getenv("CONTACT_RETENTION_DAYS", "180"))

POSITIVE_STARS = 4          # 4 and 5 stars count as satisfied
FEEDBACK_MAX_LENGTH = 1000


class NotFound(Exception):
    status_code = 404


class Forbidden(Exception):
    status_code = 403


class Conflict(Exception):
    status_code = 409


class InvalidInput(ValueError):
    """Bad user input; the message is shown to the user."""
    status_code = 400


def _hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_consultation(kind, expert_keys, problem=None, result=None):
    """Record a completed consultation. Returns {"id", "token"} for the client."""
    consultation_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)

    with db.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO consultations (id, kind, expert_keys, token_hash, problem, result_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (consultation_id, kind, json.dumps(list(expert_keys)), _hash_token(token),
             problem, json.dumps(result) if result is not None else None, db.utc_now()),
        )

    purge_expired_content()
    return {"id": consultation_id, "token": token}


def get_authorized(consultation_id, token):
    """Return the consultation row if the token matches, else raise."""
    if not consultation_id or not token:
        raise Forbidden("A consultation ID and access token are required.")

    with db.connection() as conn:
        row = conn.execute("SELECT * FROM consultations WHERE id = ?", (consultation_id,)).fetchone()

    # Same response for unknown IDs and wrong tokens, so IDs can't be probed.
    if row is None or not hmac.compare_digest(row["token_hash"], _hash_token(token)):
        raise Forbidden("This consultation could not be found or the access token is invalid.")
    return row


def delete_content(consultation_id, token):
    """
    Delete a consultation's stored content (problem, results, live transcript
    and summary). The anonymous completion record stays, so the
    consultation count is not changed retroactively.
    """
    get_authorized(consultation_id, token)
    with db.connection(write=True) as conn:
        _purge(conn, "id = ?", (consultation_id,))


def _purge(conn, where, params):
    ids = [r["id"] for r in conn.execute(f"SELECT id FROM consultations WHERE {where}", params)]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    conn.execute(
        f"DELETE FROM live_messages WHERE session_id IN"
        f" (SELECT id FROM live_sessions WHERE consultation_id IN ({marks}))", ids,
    )
    conn.execute(
        f"UPDATE live_sessions SET summary_json = NULL, summary_error = NULL, status = 'closed',"
        f" closed_at = COALESCE(closed_at, ?) WHERE consultation_id IN ({marks})", (db.utc_now(), *ids),
    )
    conn.execute(
        f"UPDATE consultations SET problem = NULL, result_json = NULL, content_deleted_at = ?"
        f" WHERE id IN ({marks})", (db.utc_now(), *ids),
    )
    return len(ids)


def purge_expired_content():
    """Apply the retention policy. Cheap enough to run on every new consultation."""
    content_cutoff = (datetime.now(timezone.utc) - timedelta(days=CONTENT_RETENTION_DAYS)).isoformat()
    contact_cutoff = (datetime.now(timezone.utc) - timedelta(days=CONTACT_RETENTION_DAYS)).isoformat()
    try:
        with db.connection(write=True) as conn:
            _purge(conn, "content_deleted_at IS NULL AND created_at < ?", (content_cutoff,))
            conn.execute("DELETE FROM contact_messages WHERE created_at < ?", (contact_cutoff,))
    except Exception as exc:
        print(f"[retention] Purge failed: {exc}")


# ─── Ratings ─────────────────────────────────────────────────────────────────

def add_rating(consultation_id, token, stars, feedback=""):
    if not isinstance(stars, int) or isinstance(stars, bool) or not 1 <= stars <= 5:
        raise InvalidInput("Please choose a rating from 1 to 5 stars.")

    feedback = (feedback or "").strip()
    if len(feedback) > FEEDBACK_MAX_LENGTH:
        raise InvalidInput(f"Feedback must be {FEEDBACK_MAX_LENGTH} characters or fewer.")

    get_authorized(consultation_id, token)

    try:
        with db.connection(write=True) as conn:
            conn.execute(
                "INSERT INTO ratings (consultation_id, stars, feedback, created_at) VALUES (?, ?, ?, ?)",
                (consultation_id, stars, feedback or None, db.utc_now()),
            )
    except sqlite3.IntegrityError as exc:
        raise Conflict("This consultation has already been rated. Thank you!") from exc


def rating_status(consultation_id, token):
    get_authorized(consultation_id, token)
    with db.connection() as conn:
        row = conn.execute("SELECT stars FROM ratings WHERE consultation_id = ?", (consultation_id,)).fetchone()
    return {"rated": row is not None, "stars": row["stars"] if row else None}


# ─── Statistics ──────────────────────────────────────────────────────────────

def _satisfaction(positive, total):
    return round(positive / total * 100, 1) if total else None


def platform_stats():
    from services import metrics

    with db.connection() as conn:
        completed = conn.execute(
            "SELECT COUNT(*) FROM consultations WHERE status = 'completed'"
        ).fetchone()[0]
        ratings = conn.execute(
            "SELECT COUNT(*) AS total, SUM(stars >= ?) AS positive, AVG(stars) AS average FROM ratings",
            (POSITIVE_STARS,),
        ).fetchone()
        rows = conn.execute(
            "SELECT c.expert_keys, r.stars FROM consultations c"
            " LEFT JOIN ratings r ON r.consultation_id = c.id WHERE c.status = 'completed'"
        ).fetchall()

    experts = {key: {"consultations": 0, "ratings": 0, "positive": 0, "star_total": 0}
               for key in expert_manager.get_all_experts()}

    # A panel consultation counts once for each expert who took part.
    for row in rows:
        for key in json.loads(row["expert_keys"]):
            stats = experts.get(key)
            if stats is None:
                continue
            stats["consultations"] += 1
            if row["stars"] is not None:
                stats["ratings"] += 1
                stats["star_total"] += row["stars"]
                stats["positive"] += row["stars"] >= POSITIVE_STARS

    response = metrics.average_single_expert_seconds()
    total_ratings = ratings["total"] or 0

    return {
        "completed_consultations": completed,
        "active_experts": len(expert_manager.get_all_experts()),
        "ratings": {
            "total": total_ratings,
            "positive": ratings["positive"] or 0,
            "satisfaction_rate": _satisfaction(ratings["positive"] or 0, total_ratings),
            "average_stars": round(ratings["average"], 2) if ratings["average"] is not None else None,
            "positive_threshold": POSITIVE_STARS,
        },
        "response_time": {
            "average_seconds": response["average_seconds"],
            "median_seconds": response["median_seconds"],
            "samples": response["successful"],
            "target_seconds": metrics.TARGET_SECONDS,
            "window_days": metrics.WINDOW_DAYS,
            "status": "measured" if response["successful"] else "measuring",
        },
        "experts": {
            key: {
                "consultations": s["consultations"],
                "ratings": s["ratings"],
                "average_stars": round(s["star_total"] / s["ratings"], 1) if s["ratings"] else None,
                "satisfaction_rate": _satisfaction(s["positive"], s["ratings"]),
            }
            for key, s in experts.items()
        },
    }


# ─── Contact messages ────────────────────────────────────────────────────────

def save_contact_message(name, email, subject, message):
    with db.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO contact_messages (name, email, subject, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (name or None, email, subject, message, db.utc_now()),
        )
