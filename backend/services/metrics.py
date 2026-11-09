"""
Response-time measurement.

Two levels are recorded, both measured on the backend with a monotonic clock:

- operations: one row per user-facing request that uses the AI (an Expert
  Room recommendation, one chat reply, a whole panel run, a live-room round…).
  This is what users experience.
- ai_calls: one row per call through the provider router (one panel run makes
  one call per expert plus one for the synthesis). Includes the provider,
  model, attempts and time to first streamed token.

Recording never breaks a request: storage errors are logged and ignored.
"""
import json
import math
import statistics
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from services import db
from services.errors import classify_exception, TIMEOUT

# User-facing request types.
RECOMMENDATION        = "recommendation"          # Expert Room report
EXPERT_CHAT           = "expert_chat"             # Expert Room follow-up chat
CONSULTATION_ANALYSIS = "consultation_analysis"   # Start Consultation analysis
CONSULTATION_CHAT     = "consultation_chat"       # Start Consultation follow-up
PANEL                 = "panel"                   # whole Expert Panel run
LIVE_ROUND            = "live_round"              # one round in the live room
LIVE_SUMMARY          = "live_summary"            # closing summary
KNOWLEDGE             = "knowledge"

# Requests where one expert answers one question. The homepage "Average
# Response" uses only these, so it reflects a typical single-expert reply and
# isn't skewed by multi-expert panel runs or long lesson generation.
SINGLE_EXPERT_TYPES = (RECOMMENDATION, EXPERT_CHAT, CONSULTATION_ANALYSIS, CONSULTATION_CHAT)

# Performance target from the product: typical single-expert replies in < 30 s.
TARGET_SECONDS = 30

# Statistics cover a rolling window so old slow periods eventually drop out.
WINDOW_DAYS = 30


class Timer:
    def __init__(self):
        self._start = time.perf_counter()
        self.started_at = db.utc_now()
        self.first_token_ms = None

    def elapsed_ms(self):
        return int((time.perf_counter() - self._start) * 1000)

    def mark_first_token(self):
        if self.first_token_ms is None:
            self.first_token_ms = self.elapsed_ms()


def _safe_insert(sql, params):
    try:
        with db.connection(write=True) as conn:
            conn.execute(sql, params)
    except Exception as exc:
        print(f"[metrics] Could not record measurement: {exc}")


def record_operation(request_type, timer, success, error_category=None, expert_key=None):
    _safe_insert(
        "INSERT INTO operations (request_type, expert_key, started_at, first_token_ms, total_ms,"
        " success, error_category, timed_out) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (request_type, expert_key, timer.started_at, timer.first_token_ms, timer.elapsed_ms(),
         int(success), error_category, int(error_category == TIMEOUT)),
    )


def record_ai_call(request_type, timer, success, provider=None, model=None, attempts=1,
                   error_category=None, expert_key=None, streamed=False, provider_attempts=None):
    """
    One logical AI call. `provider` / `model` are the ones that answered (None
    if all failed); `provider_attempts` lists every provider tried, in order.
    """
    _safe_insert(
        "INSERT INTO ai_calls (request_type, expert_key, provider, model, started_at, first_token_ms,"
        " total_ms, success, error_category, attempts, timed_out, streamed, provider_attempts)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (request_type, expert_key, provider, model, timer.started_at, timer.first_token_ms,
         timer.elapsed_ms(), int(success), error_category, attempts,
         int(error_category == TIMEOUT), int(streamed),
         json.dumps(provider_attempts) if provider_attempts else None),
    )


@contextmanager
def track_operation(request_type, expert_key=None):
    """Time a block as one user-facing operation; failures are recorded and re-raised."""
    timer = Timer()
    try:
        yield timer
    except Exception as exc:
        record_operation(request_type, timer, False, classify_exception(exc), expert_key)
        raise
    record_operation(request_type, timer, True, None, expert_key)


# ─── Aggregates ──────────────────────────────────────────────────────────────

def percentile(sorted_values, pct):
    """Nearest-rank percentile of an already sorted list."""
    if not sorted_values:
        return None
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def summarize(rows):
    """
    rows: iterables of (total_ms, success, timed_out).
    Times are taken from successful requests only; rates use every request.
    """
    rows = list(rows)
    total = len(rows)
    durations = sorted(r[0] for r in rows if r[1])
    successes = len(durations)

    def seconds(ms):
        return None if ms is None else round(ms / 1000, 1)

    return {
        "requests": total,
        "successful": successes,
        "success_rate": round(successes / total * 100, 1) if total else None,
        "timeout_rate": round(sum(1 for r in rows if r[2]) / total * 100, 1) if total else None,
        "average_seconds": seconds(statistics.fmean(durations)) if durations else None,
        "median_seconds": seconds(statistics.median(durations)) if durations else None,
        "p95_seconds": seconds(percentile(durations, 95)),
        "within_target_rate": (
            round(sum(1 for d in durations if d <= TARGET_SECONDS * 1000) / successes * 100, 1)
            if successes else None
        ),
    }


def _since():
    return (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat(timespec="milliseconds")


def _rows(table, where="", params=()):
    with db.connection() as conn:
        return [
            (r["total_ms"], r["success"], r["timed_out"], r)
            for r in conn.execute(
                f"SELECT * FROM {table} WHERE started_at >= ? {where}", (_since(), *params)
            )
        ]


def performance_report():
    ops = _rows("operations")
    calls = _rows("ai_calls")

    def group(rows, key):
        groups = {}
        for row in rows:
            groups.setdefault(row[3][key] or "unknown", []).append(row[:3])
        return {k: summarize(v) for k, v in sorted(groups.items())}

    single = [r[:3] for r in ops if r[3]["request_type"] in SINGLE_EXPERT_TYPES]

    first_tokens = sorted(r[3]["first_token_ms"] for r in calls if r[3]["first_token_ms"] is not None)

    return {
        "window_days": WINDOW_DAYS,
        "target_seconds": TARGET_SECONDS,
        "single_expert_requests": summarize(single),
        "overall": summarize(r[:3] for r in ops),
        "by_request_type": group(ops, "request_type"),
        "by_expert": group(calls, "expert_key"),
        "by_model": group([r for r in calls if r[3]["model"]], "model"),
        "streaming_first_token_seconds": {
            "samples": len(first_tokens),
            "median": round(statistics.median(first_tokens) / 1000, 1) if first_tokens else None,
            "p95": round(percentile(first_tokens, 95) / 1000, 1) if first_tokens else None,
        },
    }


def average_single_expert_seconds():
    return summarize(r[:3] for r in _rows(
        "operations",
        f"AND request_type IN ({','.join('?' * len(SINGLE_EXPERT_TYPES))})",
        SINGLE_EXPERT_TYPES,
    ))
