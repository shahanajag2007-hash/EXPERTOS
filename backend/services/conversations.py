"""
Saved conversations: Expert Room chats and Start Consultation sessions.

Each conversation belongs to a signed-in user or, without an account, to the
browser that started it (services/auth.py). Messages are stored as they are
exchanged, so a conversation survives page reloads and server restarts and
can be reopened from the conversation history.

Messages are returned in the shape the frontend and prompts already use:
    {"type": "chat", "sender": "user"|"expert", "expert": {...}, "message": "...", "file_ids": [...]}
    {"type": "system", "message": "..."}

Retention: conversations of signed-in users are kept until deleted.
Conversations started without an account are deleted after
ANONYMOUS_RETENTION_DAYS without activity. Uploaded files not attached to any
conversation are deleted after a day.
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from services import db, files
from services.consultations import InvalidInput, NotFound
from services.expert_manager import expert_manager

KINDS = ("expert_room", "quick_consultation")
ANONYMOUS_RETENTION_DAYS = int(os.getenv("ANONYMOUS_CONVERSATION_RETENTION_DAYS", "90"))
MAX_MESSAGE_CHARS = 4000
LIST_LIMIT = 50


def _title(text, fallback):
    text = " ".join((text or "").split())
    if not text:
        return fallback
    return text if len(text) <= 80 else text[:79].rstrip() + "…"


def _loads(value, default):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def create(owner, kind, expert_key, project="", answers=None, report=None, consultation_id=None, title=None):
    if kind not in KINDS:
        raise ValueError(kind)
    conversation_id = str(uuid.uuid4())
    now = db.utc_now()
    user_id, client_hash = owner.columns()
    with db.connection(write=True) as conn:
        conn.execute(
            "INSERT INTO conversations (id, kind, user_id, client_hash, expert_key, active_expert, title,"
            " project, answers_json, report_json, consultation_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, kind, user_id, client_hash, expert_key, expert_key,
             _title(title or (answers or {}).get("project_name") or project, f"{expert_key} consultation"),
             project or "", json.dumps(answers) if answers is not None else None,
             json.dumps(report) if report is not None else None, consultation_id, now, now),
        )
    purge_expired()
    return conversation_id


def get(owner, conversation_id, kind=None):
    """The conversation row if it belongs to owner (else NotFound, so IDs can't be probed)."""
    if not isinstance(conversation_id, str) or not conversation_id:
        raise NotFound("This conversation could not be found.")
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    if row is None or not owner.owns(row) or (kind and row["kind"] != kind):
        raise NotFound("This conversation could not be found. It may have been deleted.")
    return row


def messages(conversation_id):
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
    out = []
    for row in rows:
        if row["role"] == "system":
            out.append({"type": "system", "message": row["content"]})
            continue
        item = {
            "type": "chat",
            "sender": "user" if row["role"] == "user" else "expert",
            "message": row["content"],
            "created_at": row["created_at"],
        }
        if row["role"] == "expert":
            item["expert"] = expert_manager.get_expert(row["expert_key"]) or {"name": row["expert_key"]}
            item["expert_key"] = row["expert_key"]
        file_ids = _loads(row["file_ids"], [])
        if file_ids:
            item["file_ids"] = file_ids
        out.append(item)
    return out


def add_messages(conversation_id, items, active_expert=None):
    """
    Append messages atomically: items are (role, expert_key, content, file_ids).
    A user message is stored together with the reply to it, so a failed AI
    request never leaves an unanswered or duplicated question behind.
    """
    now = db.utc_now()
    with db.connection(write=True) as conn:
        conn.executemany(
            "INSERT INTO conversation_messages (conversation_id, role, expert_key, content, file_ids, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(conversation_id, role, expert_key, content, json.dumps(file_ids) if file_ids else None, now)
             for role, expert_key, content, file_ids in items],
        )
        if active_expert:
            conn.execute("UPDATE conversations SET updated_at = ?, active_expert = ? WHERE id = ?",
                         (now, active_expert, conversation_id))
        else:
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))


def update_report(conversation_id, answers=None, report=None, consultation_id=None, project=None, title=None):
    sets, params = ["updated_at = ?"], [db.utc_now()]
    if answers is not None:
        sets.append("answers_json = ?")
        params.append(json.dumps(answers))
    if report is not None:
        sets.append("report_json = ?")
        params.append(json.dumps(report))
    if consultation_id is not None:
        sets.append("consultation_id = ?")
        params.append(consultation_id)
    if project is not None:
        sets.append("project = ?")
        params.append(project)
    if title:
        sets.append("title = ?")
        params.append(_title(title, title))
    with db.connection(write=True) as conn:
        conn.execute(f"UPDATE conversations SET {', '.join(sets)} WHERE id = ?", (*params, conversation_id))


def summary(row, message_count=None):
    return {
        "id": row["id"],
        "kind": row["kind"],
        "expert_key": row["expert_key"],
        "active_expert": row["active_expert"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "message_count": message_count,
    }


def detail(row):
    attached = files.list_for_conversation(row["id"])
    history = messages(row["id"])
    return {
        **summary(row, sum(1 for m in history if m["type"] == "chat")),
        "project": row["project"],
        "answers": _loads(row["answers_json"], None),
        "report": _loads(row["report_json"], None),
        "expert": expert_manager.get_expert(row["active_expert"]),
        "messages": history,
        "files": [files.public(f) for f in attached],
    }


def list_for(owner, kind=None, expert_key=None, limit=LIST_LIMIT):
    if not owner.known:
        return []
    where, params = [], []
    if owner.user_id:
        where.append("user_id = ?")
        params.append(owner.user_id)
    else:
        where.append("user_id IS NULL AND client_hash = ?")
        params.append(owner.client_hash)
    if kind:
        if kind not in KINDS:
            raise InvalidInput("Unknown conversation type.")
        where.append("kind = ?")
        params.append(kind)
    if expert_key:
        where.append("expert_key = ?")
        params.append(expert_key)
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM conversation_messages m"
            "  WHERE m.conversation_id = c.id AND m.role != 'system') AS message_count"
            f" FROM conversations c WHERE {' AND '.join(where)} ORDER BY updated_at DESC LIMIT ?",
            (*params, max(1, min(int(limit), LIST_LIMIT))),
        ).fetchall()
    return [summary(r, r["message_count"]) for r in rows]


def delete(owner, conversation_id):
    get(owner, conversation_id)
    attached = files.list_for_conversation(conversation_id)
    with db.connection(write=True) as conn:
        conn.execute("DELETE FROM uploaded_files WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    files.delete_rows_files(attached)


def purge_expired():
    """Retention: idle anonymous conversations and unattached uploads."""
    now = datetime.now(timezone.utc)
    conversation_cutoff = (now - timedelta(days=ANONYMOUS_RETENTION_DAYS)).isoformat()
    upload_cutoff = (now - timedelta(days=1)).isoformat()
    try:
        with db.connection(write=True) as conn:
            stale = conn.execute(
                "SELECT f.* FROM uploaded_files f LEFT JOIN conversations c ON c.id = f.conversation_id"
                " WHERE (f.conversation_id IS NULL AND f.created_at < ?)"
                " OR (c.user_id IS NULL AND c.updated_at < ?)",
                (upload_cutoff, conversation_cutoff),
            ).fetchall()
            conn.executemany("DELETE FROM uploaded_files WHERE id = ?", [(r["id"],) for r in stale])
            conn.execute("DELETE FROM conversations WHERE user_id IS NULL AND updated_at < ?",
                         (conversation_cutoff,))
        files.delete_rows_files(stale)
    except db.DatabaseError as exc:
        print(f"[retention] Conversation purge failed: {exc}")
