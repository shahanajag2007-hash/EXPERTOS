"""
Live multi-expert consultation room.

Opened from a completed Expert Panel consultation. The session moves through
these phases; the backend is the source of truth and enforces them:

  expert_discussion  The experts work through the AGENDA in order. Each agenda
                     round lets up to LIVE_TURNS_PER_ROUND experts who haven't
                     yet spoken on the current item speak. An item is complete
                     only when enough different experts (stage_speakers_needed)
                     have contributed to it; failed turns don't count. Client
                     messages are rejected in this phase.
  user_interaction   After the last item, the client can talk to the panel. A
                     client round answers the message: the addressed or most
                     relevant expert(s) reply; another expert may add a point or
                     PASS. Greetings and other social messages get one brief
                     reply (services/intent.py).
  closed             "End & Summarize": no more rounds; the summary (Key
                     Takeaways) is generated from the full transcript once any
                     running turn has finished. The transcript is kept.

Nothing is generated in the background: the browser requests each round (it
requests agenda rounds automatically until the agenda is complete). Within a
round the experts speak one after another, because each one must see what the
previous one said.

Concurrency: only one round per session runs at a time. The lock is a
`busy_since` column claimed with a conditional UPDATE, so it also holds across
processes; a crashed round's lock expires after LOCK_STALE_SECONDS. Client
messages carry a client-generated ID, so a resubmitted message is ignored.
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from providers.provider_router import generate, stream
from services import db, metrics
from services.consultations import Conflict, Forbidden, InvalidInput, NotFound, get_authorized
import time

from services import intent
from services.errors import AIServiceError, USER_MESSAGES, UNKNOWN, classify_exception
from services.expert_manager import expert_manager, ALIASES, TOPICS, _contains_word

AGENDA = [
    {
        "key": "review",
        "label": "Reviewing the project",
        "instruction": (
            "Give your opening read of the project from your specialty: its most important "
            "strength and its most important weakness. React to the other experts' panel "
            "analyses where they touch your area."
        ),
    },
    {
        "key": "trade_offs",
        "label": "Discussing trade-offs",
        "instruction": (
            "Discuss the most important trade-off in your area (cost, performance, security, "
            "user experience, complexity) and where your recommendation conflicts with or "
            "depends on another expert's. Name them."
        ),
    },
    {
        "key": "clarification",
        "label": "Clarifying with the client",
        "instruction": (
            "Name the one missing fact from the client that would most change your "
            "recommendation, and the assumption you are making until they answer (the client "
            "joins the discussion once the agenda is complete). If nothing is missing, discuss "
            "dependencies and implementation order."
        ),
    },
    {
        "key": "disagreements",
        "label": "Resolving disagreements",
        "instruction": (
            "Name any disagreement with another expert that is still unresolved, state your "
            "position and what would settle it, and point out the most serious remaining risk."
        ),
    },
    {
        "key": "convergence",
        "label": "Converging on a recommendation",
        "instruction": (
            "Say what the final recommendation must include from your area, building on the "
            "points others made, and what should be done first."
        ),
    },
]

TURNS_PER_ROUND    = int(os.getenv("LIVE_TURNS_PER_ROUND", "2"))
# Different experts who must contribute to an agenda item before it is done
# (capped at the number of participants).
STAGE_SPEAKERS     = int(os.getenv("LIVE_STAGE_SPEAKERS", "3"))
# Client questions answered per session: a cost ceiling, not a conversation
# length (prompts use a recent-message window). Agenda rounds don't count.
MAX_ROUNDS         = int(os.getenv("LIVE_MAX_ROUNDS", "40"))
# How long "End & Summarize" waits for a turn that is being written.
CLOSE_WAIT_SECONDS = 90
MAX_CLIENT_SPEAKERS = 3
MAX_CLIENT_CHARS   = 2000
TRANSCRIPT_WINDOW  = 16      # recent messages included in each prompt
TURN_MAX_TOKENS    = 400
LOCK_STALE_SECONDS = 300
PASS_TOKEN         = "PASS"

SUMMARY_LIST_FIELDS = (
    "main_problems", "agreements", "disagreements", "decisions",
    "risks", "next_steps", "unanswered_questions",
)
SUMMARY_TEXT_FIELDS = ("project_understanding", "recommended_solution", "conclusion")

DISCUSSION, INTERACTION, CLOSED = "expert_discussion", "user_interaction", "closed"


# ─── Loading ─────────────────────────────────────────────────────────────────

def _session_row(conn, session_id):
    row = conn.execute("SELECT * FROM live_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise NotFound("This live session could not be found.")
    return row


def _authorize_session(session_id, token):
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM live_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        # Same answer as a wrong token, so session IDs can't be probed.
        raise Forbidden("This live session could not be found or the access token is invalid.")
    consultation = get_authorized(row["consultation_id"], token)
    return row, consultation


def _participants(consultation):
    result = json.loads(consultation["result_json"] or "{}")
    keys = [r["expert_key"] for r in result.get("responses", []) if r.get("status") == "success"]
    return [k for k in keys if expert_manager.get_expert(k)]


def _expert_public(key):
    expert = expert_manager.get_expert(key) or {}
    return {
        "key": key,
        "name": expert.get("name", key),
        "first_name": expert.get("name", key).split(" ")[0],
        "role": expert.get("role", key),
        "emoji": expert.get("emoji", "👤"),
    }


def _message_public(row):
    return {
        "id": row["id"],
        "seq": row["seq"],
        "role": row["role"],
        "expert_key": row["expert_key"],
        "content": row["content"],
        "agenda_stage": row["agenda_stage"],
        "created_at": row["created_at"],
    }


def stage_speakers_needed(participants):
    return max(1, min(len(participants), STAGE_SPEAKERS))


def _stage_speakers(messages, stage):
    """Experts who have contributed to agenda item `stage`."""
    return {m["expert_key"] for m in messages if m["role"] == "expert" and m.get("agenda_stage") == stage}


def _phase(row):
    if row["status"] != "active":
        return CLOSED
    return INTERACTION if row["stage"] >= len(AGENDA) else DISCUSSION


def _messages(conn, session_id):
    return [
        _message_public(r)
        for r in conn.execute(
            "SELECT * FROM live_messages WHERE session_id = ? ORDER BY seq", (session_id,)
        )
    ]


def _state(conn, session_id, consultation):
    row = _session_row(conn, session_id)
    stage = row["stage"]
    participants = _participants(consultation)
    messages = _messages(conn, session_id)
    phase = _phase(row)
    client_rounds = sum(1 for m in messages if m["role"] == "client")
    return {
        "id": row["id"],
        "consultation_id": row["consultation_id"],
        "status": row["status"],
        # expert_discussion | user_interaction | closed (see module docstring)
        "phase": phase,
        "can_message": phase == INTERACTION and client_rounds < MAX_ROUNDS,
        "busy": row["busy_since"] is not None,
        "rounds": client_rounds,
        "max_rounds": MAX_ROUNDS,
        "stage": stage,
        "agenda": [{"key": a["key"], "label": a["label"]} for a in AGENDA],
        "current_stage_label": AGENDA[stage]["label"] if stage < len(AGENDA) else None,
        "agenda_complete": stage >= len(AGENDA),
        "stage_speakers_needed": stage_speakers_needed(participants),
        "stage_speakers_done": len(_stage_speakers(messages, stage)) if stage < len(AGENDA) else None,
        "participants": [_expert_public(k) for k in participants],
        "problem": consultation["problem"],
        "messages": messages,
        "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
        "summary_error": row["summary_error"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
    }


# ─── Session lifecycle ───────────────────────────────────────────────────────

def open_session(consultation_id, token):
    """Create the live session for a panel consultation, or return the existing one."""
    consultation = get_authorized(consultation_id, token)

    if consultation["kind"] != "panel":
        raise Conflict("Live interaction is available for Expert Panel consultations.")
    if consultation["content_deleted_at"]:
        raise Conflict("This consultation's content has been deleted.")
    if len(_participants(consultation)) < 2:
        raise Conflict("Live interaction needs at least two experts who answered in the panel.")

    with db.connection(write=True) as conn:
        existing = conn.execute(
            "SELECT id FROM live_sessions WHERE consultation_id = ? ORDER BY created_at DESC LIMIT 1",
            (consultation_id,),
        ).fetchone()

        if existing:
            session_id = existing["id"]
        else:
            session_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO live_sessions (id, consultation_id, created_at) VALUES (?, ?, ?)",
                (session_id, consultation_id, db.utc_now()),
            )

        return _state(conn, session_id, consultation)


def get_session(session_id, token):
    _, consultation = _authorize_session(session_id, token)
    with db.connection() as conn:
        return _state(conn, session_id, consultation)


def _acquire(session_id):
    stale = (datetime.now(timezone.utc) - timedelta(seconds=LOCK_STALE_SECONDS)).isoformat(timespec="milliseconds")
    with db.connection(write=True) as conn:
        claimed = conn.execute(
            "UPDATE live_sessions SET busy_since = ? WHERE id = ? AND status = 'active'"
            " AND (busy_since IS NULL OR busy_since < ?)",
            (db.utc_now(), session_id, stale),
        ).rowcount
        if claimed:
            return
        row = _session_row(conn, session_id)
    if row["status"] != "active":
        raise Conflict("This live session has ended.")
    raise Conflict("The experts are still responding. Please wait for them to finish.")


def _release(session_id):
    try:
        with db.connection(write=True) as conn:
            conn.execute("UPDATE live_sessions SET busy_since = NULL WHERE id = ?", (session_id,))
    except Exception as exc:
        print(f"[LiveEngine] Could not release lock for {session_id}: {exc}")


def _is_active(session_id):
    with db.connection() as conn:
        return _session_row(conn, session_id)["status"] == "active"


def _append_message(session_id, role, content, expert_key=None, client_message_id=None, agenda_stage=None):
    with db.connection(write=True) as conn:
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM live_messages WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO live_messages (session_id, seq, role, expert_key, content, client_message_id,"
            " agenda_stage, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, seq, role, expert_key, content, client_message_id, agenda_stage, db.utc_now()),
        )
        return _message_public(
            conn.execute("SELECT * FROM live_messages WHERE id = ?", (cur.lastrowid,)).fetchone()
        )


# ─── Speaker selection ───────────────────────────────────────────────────────

def _last_spoke(messages):
    last = {}
    for m in messages:
        if m["role"] == "expert":
            last[m["expert_key"]] = m["seq"]
    return last


def _least_recent(participants, messages, exclude=()):
    last = _last_spoke(messages)
    candidates = [p for p in participants if p not in exclude]
    # Never-spoken first, then whoever spoke longest ago; ties keep panel order.
    return sorted(candidates, key=lambda p: (last.get(p, -1), participants.index(p)))


def _relevant_expert(participants, question):
    """The expert the client addressed by name, or whose topics the question matches best."""
    text = question.lower()
    for key in participants:
        first = (expert_manager.get_expert(key) or {}).get("name", "").split(" ")[0].lower()
        if first and _contains_word(text, first):
            return key

    best_key, best_score = None, 0
    for key in participants:
        words = ALIASES.get(key, []) + TOPICS.get(key, [])
        score = sum(1 for w in words if _contains_word(text, w))
        if score > best_score:
            best_key, best_score = key, score
    return best_key


def _addressed(participants, text):
    """Experts the client named, in panel order."""
    lowered = text.lower()
    named = []
    for key in participants:
        first = (expert_manager.get_expert(key) or {}).get("name", "").split(" ")[0].lower()
        if first and _contains_word(lowered, first):
            named.append(key)
    return named


def _topic_scores(participants, text):
    lowered = text.lower()
    return {
        key: sum(1 for w in ALIASES.get(key, []) + TOPICS.get(key, []) if _contains_word(lowered, w))
        for key in participants
    }


def choose_speakers(participants, messages, client_message=None, stage=None):
    """
    Returns a list of (expert_key, optional) for the round.
    Optional speakers may PASS if they have nothing useful to add.

    Agenda round: experts who haven't yet contributed to the current item,
    least recent speaker first, up to TURNS_PER_ROUND.

    Client round:
      - a greeting or other social message gets one reply (the addressed
        expert, else whoever spoke least recently);
      - otherwise every expert the client named answers (up to
        MAX_CLIENT_SPEAKERS); if none was named, the expert whose topics match
        best answers, plus another clearly relevant expert, or failing that one
        other expert who may PASS.
    """
    if client_message is None:
        done = _stage_speakers(messages, stage)
        pending = [k for k in _least_recent(participants, messages) if k not in done]
        return [(key, False) for key in pending[:TURNS_PER_ROUND]]

    named = _addressed(participants, client_message)

    if intent.is_social(client_message):
        return [((named or _least_recent(participants, messages))[0], False)]

    if named:
        return [(key, False) for key in named[:MAX_CLIENT_SPEAKERS]]

    scores = _topic_scores(participants, client_message)
    relevant = sorted((k for k in participants if scores[k] > 0),
                      key=lambda k: (-scores[k], participants.index(k)))
    if len(relevant) >= 2:
        return [(key, False) for key in relevant[:2]]

    primary = relevant[0] if relevant else _least_recent(participants, messages)[0]
    others = _least_recent(participants, messages, exclude=(primary,))
    return [(primary, False)] + ([(others[0], True)] if others else [])


# ─── Prompts ─────────────────────────────────────────────────────────────────

def _speaker_label(message):
    if message["role"] == "client":
        return "Client"
    if message["role"] == "system":
        return "System"
    e = _expert_public(message["expert_key"])
    return f"{e['first_name']} ({e['role']})"


def build_turn_prompt(expert_key, participants, consultation, messages, stage=None,
                      client_message=None, optional=False):
    me = _expert_public(expert_key)
    others = [_expert_public(k) for k in participants if k != expert_key]
    result = json.loads(consultation["result_json"] or "{}")

    analyses = "\n\n".join(
        f"{_expert_public(r['expert_key'])['first_name']} ({r.get('expert_role', '')}):\n"
        f"{r['response'][:700]}"
        for r in result.get("responses", [])
        if r.get("status") == "success" and r["expert_key"] in participants
    )
    verdict = ((result.get("synthesis") or {}).get("panel_verdict") or "").strip()

    transcript = "\n".join(
        f"{_speaker_label(m)}: {m['content']}" for m in messages[-TRANSCRIPT_WINDOW:]
    ) or "(The live discussion is just starting.)"

    if client_message:
        kind = intent.classify(client_message)
        task = (
            f'The client just said: "{client_message}"\n'
            f"{intent.guidance(kind)}\n"
            "The panel has finished its agenda discussion (above), and the client is now talking to "
            "the panel. Don't restart the agenda or repeat points already made; build on the "
            "discussion and refer to earlier recommendations when relevant."
        )
        if kind in intent.SOCIAL_INTENTS:
            task += " You may welcome them and invite questions about the panel's conclusions."
        else:
            task += " Answer from your specialty. If another expert already answered above, add to it or disagree with reasons instead of repeating it."
        if optional:
            task += (
                "\nAnother expert has already answered the client above. Reply only if you have a "
                "genuinely different, useful point (agreement with a caveat, disagreement, or a "
                f"constraint from your area). Otherwise reply with exactly: {PASS_TOKEN}"
            )
    else:
        item = AGENDA[stage]
        task = (
            f"Agenda item {stage + 1} of {len(AGENDA)}: {item['label']}\n{item['instruction']}\n"
            "The client is listening and will join the discussion once the agenda is complete; "
            "talk with the other experts, not to the client."
        )

    # Answering the client, models tend to restate their last agenda turn;
    # show the expert its own earlier points so it builds on them instead.
    own = [m["content"] for m in messages if m["role"] == "expert" and m["expert_key"] == expert_key][-3:]
    own_points = (
        "\nYOUR EARLIER POINTS (don't repeat these or reuse their sentences; refer to them briefly if "
        "relevant and add something new for the client's message):\n"
        + "\n".join(f"- {_shorten(p)}" for p in own) + "\n"
    ) if client_message and own else ""

    return f"""You are {me['name']}, ExpertOS's AI {me['role']} persona, in a live consultation room
with the client and these other AI experts: {", ".join(f"{o['first_name']} ({o['role']})" for o in others)}.

PROJECT
{(consultation["problem"] or "")[:3000]}

EACH EXPERT'S INITIAL PANEL ANALYSIS (excerpts)
{analyses}

PANEL CONSENSUS SO FAR
{verdict or "Not available."}

LIVE DISCUSSION SO FAR (oldest first)
{transcript}

YOUR TASK
{task}
{own_points}
RULES
- Speak only as {me['first_name']}, from your own specialty. Never write lines for anyone else.
- {"Your first sentence must directly answer what the client just said. " if client_message else ""}2 to 5 sentences, under 110 words. Plain conversational prose: no headings, bullets or name prefix.
- When you respond to another expert, name them (e.g. "I agree with {others[0]['first_name'] if others else 'the team'}, but...").
- Agree or disagree only with reasons, and explain trade-offs.
- Do not repeat points already made in the discussion.
- Only cover topics that matter for this project.
- Don't add generic AI disclaimers, and never claim to be human.
"""


def _shorten(text, limit=220):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


# ─── Rounds ──────────────────────────────────────────────────────────────────

def run_round(session_id, token, client_message=None, client_message_id=None):
    """
    Run one discussion round. Generator of (event, payload) tuples:

      ("message", msg)                      client message stored
      ("turn_start", {"expert_key"})
      ("token", {"expert_key", "text"})
      ("message", msg)                      expert turn stored
      ("turn_skipped", {"expert_key"})      optional expert passed
      ("turn_error", {"expert_key", "error", "code"})
      ("round_done", session_state)

    Validation errors (auth, closed session, busy, duplicate, limits) are
    raised before the first event.
    """
    session, consultation = _authorize_session(session_id, token)

    if client_message is not None:
        client_message = client_message.strip()
        if not client_message:
            raise InvalidInput("Please type a message for the experts.")
        if len(client_message) > MAX_CLIENT_CHARS:
            raise InvalidInput(f"Messages must be {MAX_CLIENT_CHARS} characters or fewer.")
        if not client_message_id or len(client_message_id) > 100:
            raise InvalidInput("A message ID is required.")
    elif session["stage"] >= len(AGENDA):
        raise Conflict("The experts have covered the agenda. Ask a question or end the session for a summary.")

    if session["status"] != "active":
        raise Conflict("This live session has ended.")

    if client_message is not None:
        if session["stage"] < len(AGENDA):
            # The panel finishes its agenda first; the client can't interrupt it.
            raise Conflict("The experts are still working through the agenda. "
                           "You can send messages once they finish.")
        with db.connection() as conn:
            asked = conn.execute(
                "SELECT COUNT(*) FROM live_messages WHERE session_id = ? AND role = 'client'", (session_id,)
            ).fetchone()[0]
        if asked >= MAX_ROUNDS:
            raise Conflict("This session has reached its discussion limit. End it to see the summary.")

    _acquire(session_id)

    retry = False
    try:
        if client_message is not None:
            with db.connection() as conn:
                existing = conn.execute(
                    "SELECT seq FROM live_messages WHERE session_id = ? AND client_message_id = ?",
                    (session_id, client_message_id),
                ).fetchone()
                answered = existing and conn.execute(
                    "SELECT 1 FROM live_messages WHERE session_id = ? AND role = 'expert' AND seq > ?",
                    (session_id, existing["seq"]),
                ).fetchone()
            if answered:
                raise Conflict("This message was already sent.")
            # Stored but never answered (every expert failed): a resend is a
            # retry, so answer it without storing the message twice.
            retry = existing is not None
    except Exception:
        _release(session_id)
        raise

    return _round_events(session_id, session, consultation, client_message, client_message_id, retry)


def _round_events(session_id, session, consultation, client_message, client_message_id, retry=False):
    timer = metrics.Timer()
    participants = _participants(consultation)
    spoke = 0
    failures = []

    try:
        if client_message is not None and not retry:
            yield "message", _append_message(session_id, "client", client_message,
                                             client_message_id=client_message_id)

        with db.connection() as conn:
            messages = _messages(conn, session_id)

        # Read the stage after taking the lock: another round may have advanced it.
        with db.connection() as conn:
            current = _session_row(conn, session_id)
        stage = None if client_message is not None else current["stage"]
        if stage is not None and stage >= len(AGENDA):
            return

        for expert_key, optional in choose_speakers(participants, messages, client_message, stage):

            if not _is_active(session_id):
                break   # the client ended the session mid-round

            prompt = build_turn_prompt(expert_key, participants, consultation, messages, stage,
                                       client_message, optional)
            yield "turn_start", {"expert_key": expert_key}

            text = ""
            try:
                for chunk in stream(prompt, max_tokens=TURN_MAX_TOKENS, temperature=0.5,
                                    request_type="live_turn", expert_key=expert_key, timer=timer):
                    text += chunk
                    yield "token", {"expert_key": expert_key, "text": chunk}
            except Exception as exc:
                category = classify_exception(exc)
                failures.append(category)
                message = str(exc) if isinstance(exc, AIServiceError) else USER_MESSAGES[UNKNOWN]
                yield "turn_error", {"expert_key": expert_key, "error": message, "code": category}
                continue

            text = _clean_turn(text, expert_key)

            if optional and text.upper().strip(" .!") == PASS_TOKEN:
                yield "turn_skipped", {"expert_key": expert_key}
                continue

            if not text:
                failures.append("empty_response")
                yield "turn_error", {"expert_key": expert_key, "error": USER_MESSAGES["empty_response"],
                                     "code": "empty_response"}
                continue

            stored = _append_message(session_id, "expert", text, expert_key=expert_key, agenda_stage=stage)
            messages.append(stored)
            spoke += 1
            yield "message", stored

        with db.connection(write=True) as conn:
            conn.execute("UPDATE live_sessions SET rounds = rounds + 1 WHERE id = ?", (session_id,))
            # An agenda item is complete once enough different experts have
            # contributed to it. The stage condition makes the transition
            # happen once even if two requests race.
            if stage is not None and len(_stage_speakers(messages, stage)) >= stage_speakers_needed(participants):
                conn.execute("UPDATE live_sessions SET stage = stage + 1 WHERE id = ? AND stage = ?",
                             (session_id, stage))

        success = spoke > 0 or (client_message is not None and not failures)
        metrics.record_operation(metrics.LIVE_ROUND, timer, success,
                                 None if success else (failures[0] if failures else UNKNOWN))

    finally:
        _release(session_id)

    with db.connection() as conn:
        yield "round_done", _state(conn, session_id, consultation)


def _clean_turn(text, expert_key):
    """Strip a leading 'Name:' prefix some models add despite instructions."""
    text = text.strip()
    me = _expert_public(expert_key)
    for prefix in (f"{me['name']}:", f"{me['first_name']}:", f"{me['first_name']} ({me['role']}):"):
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


# ─── Closing and summary ─────────────────────────────────────────────────────

def close_session(session_id, token):
    """
    End the session and generate the summary. No new rounds or turns start
    once the session is closed; a turn that is already being written is
    finished and saved first, so the summary includes it.
    """
    _authorize_session(session_id, token)

    with db.connection(write=True) as conn:
        conn.execute(
            "UPDATE live_sessions SET status = 'closed', closed_at = COALESCE(closed_at, ?) WHERE id = ?",
            (db.utc_now(), session_id),
        )

    deadline = time.monotonic() + CLOSE_WAIT_SECONDS
    while time.monotonic() < deadline:
        with db.connection() as conn:
            if _session_row(conn, session_id)["busy_since"] is None:
                break
        time.sleep(0.5)

    return summarize_session(session_id, token)


def build_summary_prompt(consultation, participants, messages, stage=None):
    transcript = "\n".join(f"{_speaker_label(m)}: {m['content']}" for m in messages)
    if len(transcript) > 14000:
        # Keep the opening and the most recent part of long discussions.
        transcript = transcript[:5000] + "\n[... middle of discussion omitted ...]\n" + transcript[-9000:]

    experts = ", ".join(f"{e['first_name']} ({e['role']})" for e in map(_expert_public, participants))
    done = min(stage if stage is not None else len(AGENDA), len(AGENDA))
    agenda = "\n".join(f"{i + 1}. {a['label']}: {'completed' if i < done else 'NOT reached'}"
                        for i, a in enumerate(AGENDA))
    early = done < len(AGENDA)

    return f"""You are the ExpertOS session moderator. Write the key takeaways of this live consultation
between the client and AI experts ({experts}). Use ONLY what was actually said in the transcript.
Do not add new advice, and never state a decision, agreement or recommendation that the
transcript doesn't contain. If a section has nothing from the transcript, return an empty list
or an empty string.

AGENDA PROGRESS
{agenda}
{"The session ended before the agenda was complete. Don't present the discussion as finished, and say in the conclusion that the panel did not reach a final recommendation if it didn't." if early else ""}

PROJECT
{(consultation["problem"] or "")[:3000]}

TRANSCRIPT
{transcript}

Return ONLY valid JSON with exactly these keys:
{{
  "project_understanding": "2-3 sentences",
  "main_problems": ["main problems identified in the discussion"],
  "expert_insights": [{{"expert": "first name", "insight": "that expert's most important point"}}],
  "agreements": ["points the experts agreed on"],
  "disagreements": ["each disagreement, who held which view, and how it was resolved or that it remains open"],
  "decisions": ["decisions actually made in the discussion"],
  "risks": ["..."],
  "recommended_solution": "the solution the discussion converged on (3-5 sentences), or empty if none",
  "next_steps": ["actionable next steps, most important first"],
  "unanswered_questions": ["questions raised but not answered"],
  "conclusion": "final consolidated conclusion (2-4 sentences)"
}}
"""


def summarize_session(session_id, token):
    """Generate (or regenerate) the summary of a closed session."""
    session, consultation = _authorize_session(session_id, token)

    if session["status"] != "closed":
        raise Conflict("End the session before generating its summary.")

    if session["summary_json"]:
        return get_session(session_id, token)

    with db.connection() as conn:
        messages = _messages(conn, session_id)

    summary, error = None, None

    if not any(m["role"] == "expert" for m in messages):
        error = "There was no discussion to summarise yet."
    else:
        try:
            with metrics.track_operation(metrics.LIVE_SUMMARY):
                raw = generate(
                    build_summary_prompt(consultation, _participants(consultation), messages, session["stage"]),
                    max_tokens=2000, temperature=0.2, request_type="live_summary",
                )
                summary = parse_summary(raw)
                summary["agenda_completed"] = min(session["stage"], len(AGENDA))
                summary["agenda_total"] = len(AGENDA)
        except Exception as exc:
            print(f"[LiveEngine] Summary failed: {exc}")
            error = (
                str(exc) if isinstance(exc, AIServiceError)
                else "The summary couldn't be generated. The full transcript is still available."
            )

    with db.connection(write=True) as conn:
        conn.execute(
            "UPDATE live_sessions SET summary_json = ?, summary_error = ? WHERE id = ?",
            (json.dumps(summary) if summary else None, error, session_id),
        )

    return get_session(session_id, token)


def parse_summary(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Summary was not JSON.")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Summary was not a JSON object.")

    summary = {}
    for key in SUMMARY_TEXT_FIELDS:
        value = data.get(key, "")
        summary[key] = value.strip() if isinstance(value, str) else ""
    for key in SUMMARY_LIST_FIELDS:
        value = data.get(key, [])
        if isinstance(value, str):
            value = [value] if value.strip() else []
        summary[key] = [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []

    insights = data.get("expert_insights", [])
    summary["expert_insights"] = [
        {"expert": str(i.get("expert", "")).strip(), "insight": str(i.get("insight", "")).strip()}
        for i in (insights if isinstance(insights, list) else [])
        if isinstance(i, dict) and str(i.get("insight", "")).strip()
    ]

    if not summary["conclusion"] and not summary["recommended_solution"]:
        raise ValueError("Summary had no conclusion.")
    return summary
