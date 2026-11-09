import json
import os
import re
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime, timezone

# AI responses often contain characters (e.g. non-breaking hyphens) that the
# Windows console code page can't encode; logging them must never fail a request.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")

from flask import Flask, Response, g, request, jsonify, stream_with_context
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from services import auth, db, files as file_store, metrics, live_engine
from services import consultations as consultation_store
from services import conversations as conversation_store
from services.ai_provider import analyze_project, ask_ai, stream_ai
from services.consultation_engine import consultation_engine
from services.consultations import Conflict, Forbidden, InvalidInput, NotFound
from services.db import DatabaseError
from services.errors import (
    AIServiceError, AIResponseError, USER_MESSAGES, UNKNOWN, classify_exception,
    RATE_LIMIT, TIMEOUT, SERVER, CONNECTION, EMPTY, MALFORMED, ACCOUNT_LIMIT,
)
from services.expert_manager import expert_manager
from services.knowledge_service import get_technology
from services.expert_discovery import get_discovery
from services.expert_recommendation import generate_recommendation
from services.panel_engine import iter_panel, run_panel

app = Flask(__name__)
CORS(app)
# Uploads are checked per file in services/files.py; this caps one request.
app.config["MAX_CONTENT_LENGTH"] = file_store.MAX_FILES_PER_REQUEST * file_store.MAX_FILE_BYTES + 1024 * 1024

db.init_db()

# Header carrying a consultation's access token (kept out of URLs and logs).
TOKEN_HEADER = "X-Consultation-Token"
# Random ID the browser generates once; identifies it without an account.
CLIENT_HEADER = "X-Client-Id"

# Failures where trying again later can succeed.
RETRYABLE = {RATE_LIMIT, TIMEOUT, SERVER, CONNECTION, EMPTY, MALFORMED, UNKNOWN}


def _json_body():
    """Request JSON as a dict; an empty dict for missing or invalid bodies."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _text(data, key, default=""):
    value = data.get(key, default)
    return value.strip() if isinstance(value, str) else default


def _token():
    return request.headers.get(TOKEN_HEADER, "")


def _session_token():
    header = request.headers.get("Authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def _owner():
    """Who is making this request (services/auth.py); cached per request."""
    if "owner" not in g:
        g.owner = auth.resolve_owner(_session_token(), request.headers.get(CLIENT_HEADER, ""))
    return g.owner


def _file_ids(data):
    ids = data.get("file_ids")
    if ids is None:
        return []
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise InvalidInput("file_ids must be a list of file IDs.")
    return ids


# ─── Abuse prevention ────────────────────────────────────────────────────────

class RateLimiter:
    """Sliding-window limit per client IP, kept in memory (per process)."""

    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window = window_seconds
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            hits = self.hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


rating_limiter = RateLimiter(limit=10, window_seconds=3600)
contact_limiter = RateLimiter(limit=3, window_seconds=600)
# AI requests cost provider quota. The limit is generous for real use (a long
# consultation is well under it) but stops scripted abuse from draining the
# shared quota for everyone.
ai_limiter = RateLimiter(limit=int(os.getenv("AI_REQUESTS_PER_HOUR", "200")), window_seconds=3600)
login_limiter = RateLimiter(limit=10, window_seconds=600)
register_limiter = RateLimiter(limit=5, window_seconds=3600)
upload_limiter = RateLimiter(limit=40, window_seconds=600)


def _rate_limited(limiter, message="Too many submissions. Please try again later."):
    if limiter.allow(request.remote_addr or "unknown"):
        return None
    return jsonify({"error": message, "code": "too_many_requests", "retryable": True}), 429


def _ai_rate_limited():
    return _rate_limited(
        ai_limiter,
        "You've sent a lot of requests in the last hour. Please wait a few minutes and try again.",
    )


# ─── Error handling ──────────────────────────────────────────────────────────
# AI errors carry messages written for the user. Anything unexpected is logged
# server-side and reported generically so internals never reach the browser.

def _ai_error_fields(exc):
    """
    User-safe details of an AI failure. `code` is a category such as
    "rate_limit"; `providers` lists each provider tried and its failure
    category (no keys, hosts or raw errors); `retry_at` is when a provider is
    expected to accept requests again, if a provider reported it.
    """
    retry_at = getattr(exc, "retry_at", None)
    return {
        "code": exc.category,
        "retryable": exc.category in RETRYABLE or exc.category == ACCOUNT_LIMIT,
        "retry_at": (datetime.fromtimestamp(retry_at, timezone.utc).isoformat(timespec="seconds")
                     if retry_at else None),
        "providers": getattr(exc, "attempts", []) or [],
    }


@app.errorhandler(AIServiceError)
@app.errorhandler(AIResponseError)
def handle_ai_error(exc):
    return jsonify({"error": str(exc), **_ai_error_fields(exc)}), exc.status_code


@app.errorhandler(InvalidInput)
@app.errorhandler(NotFound)
@app.errorhandler(Forbidden)
@app.errorhandler(Conflict)
@app.errorhandler(DatabaseError)
@app.errorhandler(auth.Unauthorized)
def handle_app_error(exc):
    body = {"error": str(exc)}
    if getattr(exc, "fields", None):
        body["fields"] = exc.fields
    if isinstance(exc, auth.Unauthorized):
        body["code"] = "unauthorized"
    return jsonify(body), exc.status_code


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    if exc.code == 413:
        return jsonify({"error": f"The upload is too large. Each file can be up to "
                                 f"{file_store.MAX_FILE_BYTES // (1024 * 1024)} MB, and up to "
                                 f"{file_store.MAX_FILES_PER_REQUEST} files can be sent at once."}), 413
    return jsonify({"error": exc.description}), exc.code


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    traceback.print_exc()
    return jsonify({
        "error": "Something went wrong on the ExpertOS server. Please try again."
    }), 500


# ─── Server-sent events ──────────────────────────────────────────────────────

def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sse_error(exc):
    category = getattr(exc, "category", None) or classify_exception(exc)
    if isinstance(exc, (AIServiceError, AIResponseError, InvalidInput, Conflict, Forbidden, NotFound, DatabaseError)):
        message = str(exc)
    else:
        traceback.print_exc()
        message = USER_MESSAGES[UNKNOWN]
    fields = (_ai_error_fields(exc) if isinstance(exc, (AIServiceError, AIResponseError))
              else {"code": category, "retryable": category in RETRYABLE})
    return _sse("error", {
        "error": message,
        **fields,
        "partial": bool(getattr(exc, "partial", False)),
    })


def _sse_response(events):
    return Response(
        stream_with_context(events),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/")
def home():
    return "ExpertOS Backend Running"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ─── /analyze ────────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():

    data    = _json_body()
    project = _text(data, "prompt")

    if not project:
        return jsonify({"error": "Project description is required."}), 400
    if len(project) > 20000:
        return jsonify({"error": "Please keep the project description under 20,000 characters."}), 400

    owner = auth.require_owner(_owner())
    attached = file_store.get_owned(owner, _file_ids(data))

    limited = _ai_rate_limited()
    if limited:
        return limited

    with metrics.track_operation(metrics.CONSULTATION_ANALYSIS, "Software Architect"):
        analysis = analyze_project(project, attached)

    consultation = consultation_store.create_consultation(
        "quick_consultation", ["Software Architect"]
    )
    result = consultation_engine.start_consultation(owner, project, analysis, consultation["id"])
    file_store.attach_to_conversation(owner, [f["id"] for f in attached], result["conversation_id"])
    result["consultation"] = consultation
    return jsonify(result)


# ─── /chat ───────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    """
    Follow-up message in a Start Consultation conversation.
    Body: {"conversation_id", "message", "file_ids"?}
    """
    data    = _json_body()
    message = _text(data, "message")

    if not message:
        return jsonify({"error": "Message cannot be empty."}), 400
    if len(message) > conversation_store.MAX_MESSAGE_CHARS:
        return jsonify({"error": "Messages must be 4000 characters or fewer."}), 400

    owner = auth.require_owner(_owner())
    row = conversation_store.get(owner, _text(data, "conversation_id"), kind="quick_consultation")
    new_ids = _file_ids(data)
    new_files = file_store.get_owned(owner, new_ids)
    file_store.attach_to_conversation(owner, new_ids, row["id"])

    limited = _ai_rate_limited()
    if limited:
        return limited

    with metrics.track_operation(metrics.CONSULTATION_CHAT):
        result = consultation_engine.chat(row, message, _conversation_files(row["id"], new_files), new_ids)
    return jsonify(result)


def _conversation_files(conversation_id, new_files):
    """
    Files the expert sees for a message: every document in the conversation,
    plus images only when they are attached to this message (images are large
    and are re-sent to the AI each time they are included).
    """
    new_ids = {f["id"] for f in new_files}
    rows = [f for f in file_store.list_for_conversation(conversation_id)
            if f["kind"] == "document" or f["id"] in new_ids]
    known = {f["id"] for f in rows}
    return rows + [f for f in new_files if f["id"] not in known]


# ─── /expert/chat  (ExpertRoom standalone chat) ──────────────────────────────
# ExpertRoom uses a different flow: user has already completed the discovery
# wizard and received a recommendation.  Follow-up questions go here.
# The session is reset per-project so rooms don't share state with /consultation.

def _expert_chat_request():
    """
    Parse an Expert Room chat request. With a conversation_id the history,
    project and report come from the saved conversation (the client's copy is
    ignored) and the exchange is saved once the reply is complete. Returns
    (ask_ai kwargs, conversation row or None, file IDs attached to this message).
    """
    data       = _json_body()
    expert_key = _text(data, "expert")
    message    = _text(data, "message")

    if not message:
        raise InvalidInput("Message cannot be empty.")
    if len(message) > 4000:
        raise InvalidInput("Messages must be 4000 characters or fewer.")
    if not expert_key:
        raise InvalidInput("Expert name is required.")

    expert = expert_manager.get_expert(expert_key)
    if not expert:
        raise NotFound(f"Expert '{expert_key}' not found.")

    new_ids = _file_ids(data)
    row = None
    turn = {"switch_to": None, "notice": None, "direct_reply": None}
    conversation_id = _text(data, "conversation_id")

    if conversation_id:
        owner = auth.require_owner(_owner())
        row = conversation_store.get(owner, conversation_id, kind="expert_room")
        # The browser names the room it is in; a conversation is used only in
        # its own expert's room. Who answers is the conversation's saved
        # chatbot role (active_expert), which can differ from the room expert.
        if row["expert_key"] != expert_key:
            raise InvalidInput("This conversation belongs to a different expert's room.")
        new_files = file_store.get_owned(owner, new_ids)
        file_store.attach_to_conversation(owner, new_ids, row["id"])
        saved = conversation_store.detail(row)
        req = {
            "project":  row["project"],
            "analysis": saved["report"] or {},
            "history":  saved["messages"],
            "files":    _conversation_files(row["id"], new_files),
        }
        # The saved conversation's active expert answers, whatever the browser
        # sent. A request for another expert switches it here, in the app.
        expert_key, turn = _expert_room_switch(row["active_expert"], message)
        expert = expert_manager.get_expert(expert_key)
        req["joined"] = (
            "returning" if turn["switch_to"] == row["expert_key"] else turn["switch_to"] is not None
        )
    else:
        new_files = file_store.get_owned(_owner(), new_ids) if new_ids else []
        req = {
            "project":  _text(data, "project"),
            "analysis": data.get("analysis") or {},
            "history":  data.get("history") if isinstance(data.get("history"), list) else [],
            "files":    new_files,
        }

    req.update({"expert": expert, "expert_key": expert_key, "question": message})
    return req, row, new_ids, turn


def _expert_room_switch(active, message):
    """
    Apply an explicit request for another expert (services/expert_manager.py
    resolve_switch). Returns (expert who answers, turn details):
      switch_to     the expert switched to, or None
      notice        "Maya Chen joined the conversation." when switching
      direct_reply  an answer that needs no AI (which expert? / not available)
    """
    turn = {"switch_to": None, "notice": None, "direct_reply": None}
    decision = expert_manager.resolve_switch(message, active)
    if not decision:
        return active, turn

    if decision["action"] == "switch" and expert_manager.expert_exists(decision["expert"]):
        new = expert_manager.get_expert(decision["expert"])
        turn["switch_to"] = decision["expert"]
        turn["notice"] = f"{new['emoji']} {new['name']} joined the conversation."
        return decision["expert"], turn

    turn["direct_reply"] = expert_manager.switch_reply(decision, active)
    return active, turn


def _save_exchange(row, req, reply, file_ids, turn=None):
    if row is None:
        return
    turn = turn or {}
    items = [("user", None, req["question"], file_ids)]
    if turn.get("notice"):
        items.append(("system", None, turn["notice"], None))
    items.append(("expert", req["expert_key"], reply, None))
    # Switching and its first answer are saved together, so the conversation's
    # active expert never changes without the new expert's reply.
    conversation_store.add_messages(row["id"], items, active_expert=turn.get("switch_to"))


def _expert_public(key):
    expert = expert_manager.get_expert(key) or {}
    return {"key": key, **expert}


@app.route("/expert/chat", methods=["POST"])
def expert_chat():
    """
    Stateless expert chat for ExpertRoom.

    Body:
      {
        "expert":   "Software Architect",
        "project":  "...",
        "analysis": { ... },
        "history":  [ { "sender": "user"|"expert", "message": "..." }, ... ],
        "message":  "..."
      }
    """
    req, row, file_ids, turn = _expert_chat_request()

    limited = _ai_rate_limited()
    if limited:
        return limited

    if turn["direct_reply"]:
        reply = turn["direct_reply"]
    else:
        with metrics.track_operation(metrics.EXPERT_CHAT, req["expert_key"]):
            reply = ask_ai(**req, request_type=metrics.EXPERT_CHAT)

    _save_exchange(row, req, reply, file_ids, turn)
    return jsonify({
        "expert": req["expert"],
        "expert_key": req["expert_key"],
        "switch": turn["switch_to"] is not None,
        "notice": turn["notice"],
        "reply":  reply,
    })


@app.route("/expert/chat/stream", methods=["POST"])
def expert_chat_stream():
    """
    Same body as /expert/chat; streams the reply as server-sent events:
      switch {"expert_key", "expert", "notice"}   only when the user asked for another expert
      token {"text"} … then done {"reply", "expert_key", "saved"},
      or error {"error", "code", "retryable"}.
    The switch is saved only with the new expert's completed reply; if the
    reply fails, the previous expert stays active.
    """
    req, row, file_ids, turn = _expert_chat_request()

    limited = _ai_rate_limited()
    if limited:
        return limited

    def events():
        timer = metrics.Timer()
        reply = ""
        if turn["switch_to"]:
            yield _sse("switch", {"expert_key": turn["switch_to"], "expert": _expert_public(turn["switch_to"]),
                                  "notice": turn["notice"]})
        try:
            if turn["direct_reply"]:
                reply = turn["direct_reply"]
                yield _sse("token", {"text": reply})
            else:
                for chunk in stream_ai(**req, request_type=metrics.EXPERT_CHAT, timer=timer):
                    reply += chunk
                    yield _sse("token", {"text": chunk})
        except Exception as exc:
            metrics.record_operation(metrics.EXPERT_CHAT, timer, False,
                                     classify_exception(exc), req["expert_key"])
            yield _sse_error(exc)
            return
        if not turn["direct_reply"]:
            metrics.record_operation(metrics.EXPERT_CHAT, timer, True, None, req["expert_key"])
        try:
            _save_exchange(row, req, reply.strip(), file_ids, turn)
        except Exception as exc:
            # The reply is complete on screen; say it couldn't be saved.
            traceback.print_exc()
            yield _sse("done", {"reply": reply.strip(), "expert_key": req["expert_key"], "saved": False,
                                "save_error": "This reply couldn't be saved to your conversation history."})
            return
        yield _sse("done", {"reply": reply.strip(), "expert_key": req["expert_key"], "saved": row is not None})

    return _sse_response(events())


# ─── /panel ──────────────────────────────────────────────────────────────────

def _panel_request():
    owner = auth.require_owner(_owner())   # P1-1: panel requires a client identity
    data        = _json_body()
    expert_keys = data.get("experts") if isinstance(data.get("experts"), list) else []
    expert_keys = [k for k in expert_keys if isinstance(k, str) and k.strip()]
    problem     = _text(data, "problem")
    context     = _text(data, "context")

    if not problem:
        raise InvalidInput("Problem description is required.")

    if len(problem) > 8000:
        raise InvalidInput("Please keep the problem description under 8000 characters.")

    if not expert_keys:
        raise InvalidInput("At least one expert must be selected.")

    if len(expert_keys) > 6:
        raise InvalidInput("Maximum 6 experts per panel.")

    return expert_keys, problem, context


def _store_panel(problem, result):
    successful = [r["expert_key"] for r in result["responses"] if r["status"] == "success"]
    if not successful:
        return None
    return consultation_store.create_consultation(
        "panel", successful, problem=problem,
        result={k: result[k] for k in ("responses", "synthesis")},
    )


@app.route("/panel", methods=["POST"])
def panel():
    """
    Multi-expert panel consultation.

    Body:
      {
        "experts": ["Software Architect", "Security Expert", ...],
        "problem": "Describe the project...",
        "context": "Optional extra context"
      }

    Returns:
      {
        "responses": [ { expert_key, expert_name, expert_role, expert_emoji, status, response }, ... ],
        "synthesis": { agreements, disagreements, top_priorities, risks,
                       recommended_next_steps, panel_verdict } | null,
        "synthesis_error": "..." | null,
        "successful_count": N,
        "failed_count":     N,
        "consultation": { id, token } | null
      }
    """
    expert_keys, problem, context = _panel_request()

    limited = _ai_rate_limited()
    if limited:
        return limited

    timer = metrics.Timer()
    result = run_panel(
        expert_keys=expert_keys,
        problem=problem,
        context=context,
    )
    success = result["successful_count"] > 0
    metrics.record_operation(metrics.PANEL, timer, success, None if success else UNKNOWN)

    result["consultation"] = _store_panel(problem, result)
    return jsonify(result)


@app.route("/panel/stream", methods=["POST"])
def panel_stream():
    """
    Same body as /panel. Streams server-sent events so each expert's result
    appears as soon as it is ready:
      expert {result} (one per expert, in completion order)
      synthesis {"synthesis", "synthesis_error"}
      done {same object /panel returns}
    """
    expert_keys, problem, context = _panel_request()

    limited = _ai_rate_limited()
    if limited:
        return limited

    def events():
        timer = metrics.Timer()
        try:
            for event, payload in iter_panel(expert_keys, problem, context):
                if event == "expert":
                    timer.mark_first_token()
                    yield _sse("expert", payload)
                elif event == "synthesis":
                    yield _sse("synthesis", payload)
                elif event == "done":
                    success = payload["successful_count"] > 0
                    metrics.record_operation(metrics.PANEL, timer, success, None if success else UNKNOWN)
                    payload["consultation"] = _store_panel(problem, payload)
                    yield _sse("done", payload)
        except Exception as exc:
            metrics.record_operation(metrics.PANEL, timer, False, classify_exception(exc))
            yield _sse_error(exc)

    return _sse_response(events())


# ─── /knowledge ──────────────────────────────────────────────────────────────

@app.route("/knowledge", methods=["POST"])
def knowledge():

    data       = _json_body()
    project    = _text(data, "project")
    technology = _text(data, "technology")
    expert     = _text(data, "expert") or "Software Architect"

    if not technology:
        return jsonify({"error": "Technology is required."}), 400

    limited = _ai_rate_limited()
    if limited:
        return limited

    with metrics.track_operation(metrics.KNOWLEDGE):
        result = get_technology(project, technology, expert)
    return jsonify(result)


# ─── /expert/discovery ───────────────────────────────────────────────────────

@app.route("/expert/discovery", methods=["POST"])
def expert_discovery():

    expert = _text(_json_body(), "expert") or "Software Architect"

    return jsonify({"steps": get_discovery(expert)})


# ─── /expert/recommend ───────────────────────────────────────────────────────

@app.route("/expert/recommend", methods=["POST"])
def expert_recommend():

    data    = _json_body()
    expert  = _text(data, "expert")
    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}

    if not expert_manager.expert_exists(expert):
        return jsonify({"error": f"Expert '{expert}' not found."}), 404

    if not str(answers.get("description", "")).strip():
        return jsonify({"error": "Please describe your project so the expert has something to review."}), 400
    if len(json.dumps(answers)) > 20000:
        return jsonify({"error": "Your answers are too long. Please shorten them to under 20,000 characters."}), 400

    owner = auth.require_owner(_owner())
    attached = file_store.get_owned(owner, _file_ids(data))
    # Revising the answers updates the same conversation instead of starting another.
    existing = None
    if _text(data, "conversation_id"):
        existing = conversation_store.get(owner, _text(data, "conversation_id"), kind="expert_room")
        if existing["expert_key"] != expert:
            return jsonify({"error": "This conversation belongs to a different expert's room."}), 400
        attached = _conversation_files(existing["id"], attached)

    limited = _ai_rate_limited()
    if limited:
        return limited

    with metrics.track_operation(metrics.RECOMMENDATION, expert):
        result = generate_recommendation(expert, answers, attached)

    result["consultation"] = consultation_store.create_consultation("expert_room", [expert])
    report = {k: v for k, v in result.items() if k != "consultation"}
    project = str(answers.get("description") or answers.get("project_name") or "")
    if existing is not None:
        conversation_id = existing["id"]
        conversation_store.update_report(conversation_id, answers=answers, report=report,
                                         consultation_id=result["consultation"]["id"], project=project,
                                         title=answers.get("project_name") or project)
    else:
        conversation_id = conversation_store.create(
            owner, "expert_room", expert, project=project, answers=answers, report=report,
            consultation_id=result["consultation"]["id"],
        )
    file_store.attach_to_conversation(owner, [f["id"] for f in attached], conversation_id)
    result["conversation_id"] = conversation_id
    return jsonify(result)


# ─── /expert/match  (AI Guide) ───────────────────────────────────────────────

@app.route("/expert/match", methods=["POST"])
def expert_match():
    """
    Suggest the best starting expert for a problem description.

    Uses keyword matching against the expert registry, so it works without
    calling an AI provider. Returns the matched words so the UI can explain
    the suggestion honestly.
    """
    problem = _text(_json_body(), "problem")

    if not problem:
        return jsonify({"error": "Please describe your project or problem."}), 400

    expert_key, matched = expert_manager.recommend(problem)

    return jsonify({
        "expert_key": expert_key,
        "expert":     expert_manager.get_expert(expert_key),
        "matched":    matched,
    })


# ─── Accounts ────────────────────────────────────────────────────────────────

@app.route("/auth/register", methods=["POST"])
def auth_register():
    limited = _rate_limited(register_limiter, "Too many sign-up attempts. Please try again later.")
    if limited:
        return limited
    data = _json_body()
    result = auth.register(_text(data, "email"), data.get("password"), _text(data, "name"), _owner_anonymous())
    return jsonify(result), 201


@app.route("/auth/login", methods=["POST"])
def auth_login():
    limited = _rate_limited(login_limiter, "Too many sign-in attempts. Please wait a few minutes and try again.")
    if limited:
        return limited
    data = _json_body()
    return jsonify(auth.login(_text(data, "email"), data.get("password"), _owner_anonymous()))


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    auth.logout(_session_token())
    return jsonify({"status": "signed_out"})


@app.route("/auth/me", methods=["GET"])
def auth_me():
    return jsonify({"user": auth.current_user(_session_token())})


def _owner_anonymous():
    """The browser's identity, ignoring any (possibly expired) session token."""
    return auth.resolve_owner("", request.headers.get(CLIENT_HEADER, ""))


# ─── Saved conversations ─────────────────────────────────────────────────────

@app.route("/conversations", methods=["GET"])
def list_conversations():
    owner = _owner()
    expert = request.args.get("expert", "").strip() or None
    kind = request.args.get("kind", "").strip() or None
    return jsonify({
        "conversations": conversation_store.list_for(owner, kind=kind, expert_key=expert),
        "signed_in": bool(owner.user_id),
    })


@app.route("/conversations/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id):
    row = conversation_store.get(auth.require_owner(_owner()), conversation_id)
    return jsonify(conversation_store.detail(row))


@app.route("/conversations/<conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id):
    conversation_store.delete(auth.require_owner(_owner()), conversation_id)
    return jsonify({"status": "deleted"})


# ─── File uploads ────────────────────────────────────────────────────────────

@app.route("/files", methods=["POST"])
def upload_files():
    """
    multipart/form-data with one or more "files" fields and an optional
    "conversation_id". Returns {"files": [...]} with what was extracted.
    """
    limited = _rate_limited(upload_limiter, "Too many uploads. Please wait a few minutes and try again.")
    if limited:
        return limited

    owner = auth.require_owner(_owner())
    uploads = [f for f in request.files.getlist("files") if f and f.filename]
    if not uploads:
        raise InvalidInput("Choose at least one file to upload.")
    if len(uploads) > file_store.MAX_FILES_PER_REQUEST:
        raise InvalidInput(f"Upload at most {file_store.MAX_FILES_PER_REQUEST} files at a time.")

    conversation_id = (request.form.get("conversation_id") or "").strip() or None
    if conversation_id:
        conversation_store.get(owner, conversation_id)

    # Validate everything before storing anything, so one bad file doesn't
    # leave the others half-uploaded.
    payloads = []
    for upload in uploads:
        data = upload.read(file_store.MAX_FILE_BYTES + 1)
        file_store.extract(upload.filename, data)
        payloads.append((upload.filename, data))

    saved = [file_store.save_upload(owner, name, data, conversation_id) for name, data in payloads]
    return jsonify({"files": saved}), 201


@app.route("/files/<file_id>", methods=["DELETE"])
def delete_file(file_id):
    file_store.delete(auth.require_owner(_owner()), file_id)
    return jsonify({"status": "deleted"})


# ─── /stats ──────────────────────────────────────────────────────────────────
# Computed from stored records only; never calls an AI provider.

@app.route("/stats", methods=["GET"])
def stats():
    response = jsonify(consultation_store.platform_stats())
    response.headers["Cache-Control"] = "public, max-age=15"
    return response


@app.route("/stats/performance", methods=["GET"])
def stats_performance():
    return jsonify(metrics.performance_report())


# ─── Consultations and ratings ───────────────────────────────────────────────

@app.route("/consultations/<consultation_id>/rating", methods=["GET"])
def rating_status(consultation_id):
    return jsonify(consultation_store.rating_status(consultation_id, _token()))


@app.route("/consultations/<consultation_id>/rating", methods=["POST"])
def submit_rating(consultation_id):
    limited = _rate_limited(rating_limiter)
    if limited:
        return limited

    data = _json_body()
    consultation_store.add_rating(
        consultation_id, _token(), data.get("stars"), _text(data, "feedback"),
    )
    return jsonify({"status": "saved"}), 201


@app.route("/consultations/<consultation_id>", methods=["DELETE"])
def delete_consultation(consultation_id):
    consultation_store.delete_content(consultation_id, _token())
    return jsonify({"status": "deleted"})


# ─── Live multi-expert consultation ──────────────────────────────────────────

@app.route("/live/sessions", methods=["POST"])
def open_live_session():
    consultation_id = _text(_json_body(), "consultation_id")
    return jsonify(live_engine.open_session(consultation_id, _token()))


@app.route("/live/sessions/<session_id>", methods=["GET"])
def get_live_session(session_id):
    return jsonify(live_engine.get_session(session_id, _token()))


@app.route("/live/sessions/<session_id>/rounds", methods=["POST"])
def live_round(session_id):
    """
    Run one discussion round, streamed as server-sent events.
    Body: {} to continue the agenda, or {"message", "message_id"} for a client message.
    """
    data = _json_body()
    message = data.get("message")
    message = message if isinstance(message, str) else None

    # Validation, auth and locking happen here, before the stream starts, so
    # failures come back as normal JSON errors.
    rounds = live_engine.run_round(session_id, _token(), message, _text(data, "message_id") or None)

    def events():
        try:
            for event, payload in rounds:
                yield _sse(event, payload)
        except Exception as exc:
            yield _sse_error(exc)

    return _sse_response(events())


@app.route("/live/sessions/<session_id>/close", methods=["POST"])
def close_live_session(session_id):
    return jsonify(live_engine.close_session(session_id, _token()))


@app.route("/live/sessions/<session_id>/summary", methods=["POST"])
def retry_live_summary(session_id):
    return jsonify(live_engine.summarize_session(session_id, _token()))


# ─── Contact ─────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.route("/contact", methods=["POST"])
def contact():
    data = _json_body()

    # Honeypot: real users never see or fill this field.
    if _text(data, "website"):
        return jsonify({"status": "received"}), 201

    limited = _rate_limited(contact_limiter)
    if limited:
        return limited

    name    = _text(data, "name")
    email   = _text(data, "email")
    subject = _text(data, "subject")
    message = _text(data, "message")

    errors = {}
    if len(name) > 100:
        errors["name"] = "Name must be 100 characters or fewer."
    if not EMAIL_RE.match(email) or len(email) > 254:
        errors["email"] = "Please enter a valid email address."
    if not subject or len(subject) > 150:
        errors["subject"] = "Please enter a subject (up to 150 characters)."
    if len(message) < 10 or len(message) > 5000:
        errors["message"] = "Please write a message between 10 and 5000 characters."
    if errors:
        return jsonify({"error": "Please correct the highlighted fields.", "fields": errors}), 400

    consultation_store.save_contact_message(name, email, subject, message)
    return jsonify({"status": "received"}), 201


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from providers.provider_router import provider_router
    from services.openrouter_client import MODEL_REGISTRY

    enabled = provider_router.enabled_provider_names()
    print(f"[ExpertOS] AI providers enabled: {', '.join(enabled) or 'none (add keys to backend/.env)'}")
    print(f"[ExpertOS] OpenRouter models: {', '.join(m['id'] for m in MODEL_REGISTRY)}")
    print(f"[ExpertOS] Database: {db.db_path()}")

    import sysconfig

    # The debug reloader should only restart for changes to ExpertOS's own
    # code. Installed packages and the standard library can be touched the
    # first time a module is imported (e.g. during the first AI request:
    # observed with site-packages .pyc files and Lib\netrc.py), which would
    # restart the server mid-request. Database files are excluded too.
    # The "stat" reloader compares modification times. The default watchdog
    # reloader reacts to any filesystem event, and cloud-sync tools such as
    # OneDrive touch file attributes after syncing, which restarted the server
    # mid-request even though no code had changed.
    interpreter_dirs = {sys.base_prefix, sys.prefix, sysconfig.get_paths()["stdlib"]}
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode, threaded=True, reloader_type="stat", exclude_patterns=[
        "*site-packages*", "*__pycache__*", "*.db", "*.db-*",
        *(os.path.join(d, "*") for d in interpreter_dirs),
    ])
