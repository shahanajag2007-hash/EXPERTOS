"""
panel_engine.py — Multi-expert parallel consultation service.

Runs each selected expert's analysis concurrently via ThreadPoolExecutor,
then synthesises the individual responses into a combined recommendation.

Failure handling:
  - If one expert fails, others are preserved and displayed.
  - If synthesis fails, the individual responses are still returned.
  - Bounded retries and timeouts prevent indefinite blocking.
"""
import json
import concurrent.futures
import time
from typing import Any

from providers.provider_router import generate
from services.errors import AIServiceError
from services.expert_manager import expert_manager

# Overall time allowed for the parallel expert analyses (seconds)
_EXPERT_TIMEOUT = 120

# Synthesis timeout
_SYNTHESIS_TIMEOUT = 60

_SYNTHESIS_FIELDS = (
    "agreements", "disagreements", "top_priorities",
    "risks", "recommended_next_steps", "panel_verdict",
)


# ─── Expert prompt builder ────────────────────────────────────────────────────

def _build_expert_prompt(
    expert:   dict[str, Any],
    problem:  str,
    context:  str,
) -> str:
    return f"""
You are {expert["name"]}.

ROLE
----
You are ExpertOS's AI {expert["role"]} persona, participating in an
AI Expert Panel consultation.

Speak with the judgement of an experienced {expert["role"]}, but never
claim to be a human. Don't add generic AI disclaimers and don't mention
which AI model or provider powers you.

---------------------------------------------

YOUR SPECIALIZATION

Only answer from your domain: {expert["role"]}.

Do not repeat what other experts would say.

Focus on the aspects that belong to YOUR expertise.

---------------------------------------------

PROJECT

{problem}

---------------------------------------------

ADDITIONAL CONTEXT

{context or "No additional context provided."}

---------------------------------------------

PANEL INSTRUCTIONS

You are one of several experts reviewing this project simultaneously.

Your response will be shown alongside other expert responses.

Structure your response clearly using these sections:

## Assessment
Your professional assessment of the project from your domain perspective.

## Key Recommendations
Your top 3-5 concrete recommendations (use bullet points here only).

## Risks & Concerns
The main risks you see from your area of expertise.

## Next Steps
The immediate actions the user should take related to your domain.

IMPORTANT:
- Be direct and specific.
- Speak naturally like a senior consultant.
- Do NOT repeat the project description back.
- Do NOT say "As an AI..."
- Keep your response under 400 words.
"""


# ─── Synthesis prompt ─────────────────────────────────────────────────────────

def _build_synthesis_prompt(
    problem:   str,
    responses: list[dict[str, Any]],
) -> str:
    expert_sections = "\n\n".join([
        f"--- {r['expert_name']} ({r['expert_role']}) ---\n{r['response']}"
        for r in responses
        if r["status"] == "success"
    ])

    return f"""
You are the ExpertOS Panel Coordinator.

You have received independent analyses from multiple expert consultants.

Your job is to synthesise their recommendations into one coherent summary.

PROJECT
-------
{problem}

EXPERT RESPONSES
----------------
{expert_sections}

SYNTHESIS INSTRUCTIONS

Return ONLY valid JSON in this exact schema:

{{
    "agreements": "",
    "disagreements": "",
    "top_priorities": "",
    "risks": "",
    "recommended_next_steps": "",
    "panel_verdict": ""
}}

Field guidelines:
- agreements: What all or most experts agree on (2-3 sentences).
- disagreements: Where experts differ or have conflicting advice (2-3 sentences, or "None identified" if not applicable).
- top_priorities: The 3 most important actions based on all expert input (2-3 sentences).
- risks: The most critical cross-domain risks identified (2-3 sentences).
- recommended_next_steps: Concrete next steps combining all expert advice (3-4 sentences).
- panel_verdict: One paragraph overall verdict (3-4 sentences).

Rules:
- Every field must be a string.
- No nested objects or arrays.
- No markdown inside field values.
- Return ONLY valid JSON without any markdown code blocks.
"""


# ─── Single expert call ───────────────────────────────────────────────────────

def _consult_expert(
    expert_key: str,
    problem:    str,
    context:    str,
) -> dict[str, Any]:
    """Called in a thread. Returns a result dict regardless of success/failure."""
    expert = expert_manager.get_expert(expert_key)

    if not expert:
        return {
            "expert_key":  expert_key,
            "expert_name": expert_key,
            "expert_role": "Unknown",
            "expert_emoji": "❓",
            "status":      "error",
            "response":    f"Expert '{expert_key}' not found.",
        }

    try:
        prompt   = _build_expert_prompt(expert, problem, context)
        response = generate(prompt, max_tokens=1500, temperature=0.3,
                            request_type="panel_expert", expert_key=expert_key)

        return {
            "expert_key":  expert_key,
            "expert_name": expert["name"],
            "expert_role": expert["role"],
            "expert_emoji": expert.get("emoji", "👤"),
            "status":      "success",
            "response":    response,
        }

    except Exception as exc:
        print(f"[PanelEngine] Expert '{expert_key}' failed: {exc}")
        return {
            "expert_key":  expert_key,
            "expert_name": expert.get("name", expert_key),
            "expert_role": expert.get("role", "Expert"),
            "expert_emoji": expert.get("emoji", "👤"),
            "status":      "error",
            "response":    (
                str(exc) if isinstance(exc, AIServiceError) else
                "This expert is temporarily unavailable. "
                "Please try again or consult another expert."
            ),
        }


def _error_result(key: str, message: str) -> dict[str, Any]:
    expert = expert_manager.get_expert(key) or {}
    return {
        "expert_key":  key,
        "expert_name": expert.get("name", key),
        "expert_role": expert.get("role", "Expert"),
        "expert_emoji": expert.get("emoji", "👤"),
        "status":      "error",
        "response":    message,
    }


# ─── Synthesis ────────────────────────────────────────────────────────────────

def synthesize(problem: str, successful: list[dict[str, Any]]):
    """Return (synthesis, synthesis_error). Never raises."""
    try:
        prompt = _build_synthesis_prompt(problem, successful)
        raw    = generate(prompt, max_tokens=1200, temperature=0.2,
                          request_type="panel_synthesis")

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        # Extract JSON object
        start = raw.find("{")
        end   = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start:end + 1]

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Synthesis was not a JSON object.")

        # Keep only the expected string fields.
        synthesis = {
            key: value if isinstance(value, str) else json.dumps(value)
            for key, value in parsed.items()
            if key in _SYNTHESIS_FIELDS and value
        } or None

        if synthesis is None:
            raise ValueError("Synthesis contained no usable fields.")

        return synthesis, None

    except Exception as exc:
        # Individual responses are still returned; the UI shows that the
        # combined recommendation could not be produced.
        print(f"[PanelEngine] Synthesis failed: {exc}")
        return None, (
            "The combined recommendation could not be generated this time. "
            "The individual expert responses above are complete."
        )


# ─── Panel Engine ─────────────────────────────────────────────────────────────

def iter_panel(
    expert_keys: list[str],
    problem:     str,
    context:     str = "",
):
    """
    Run a parallel multi-expert consultation, yielding events as they happen:

      ("expert", result)       — as soon as each expert finishes (any order)
      ("synthesis", {"synthesis": ..., "synthesis_error": ...})
      ("done", summary)        — same shape run_panel() returns

    Expert analyses are independent, so they run concurrently. The synthesis
    needs their output, so it starts only after all of them have finished or
    the expert timeout has passed.
    """
    # Remove duplicates while preserving order
    seen = set()
    unique_keys = [k for k in expert_keys if not (k in seen or seen.add(k))]

    responses: list[dict[str, Any]] = []

    if unique_keys:
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(len(unique_keys), 6),
            thread_name_prefix="panel-expert",
        )

        future_to_key = {
            executor.submit(_consult_expert, key, problem, context): key
            for key in unique_keys
        }

        pending = set(future_to_key)
        deadline = time.monotonic() + _EXPERT_TIMEOUT

        # wait() never raises on timeout, so experts that finished in time are
        # kept even when another expert is still running.
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            done, pending = concurrent.futures.wait(
                pending, timeout=remaining, return_when=concurrent.futures.FIRST_COMPLETED,
            )

            for future in done:
                key = future_to_key[future]
                try:
                    result = future.result()
                except Exception as exc:
                    print(f"[PanelEngine] Expert '{key}' raised: {exc}")
                    result = _error_result(
                        key, "This expert ran into an unexpected error. Please try again."
                    )
                responses.append(result)
                yield "expert", result

        for future in pending:
            result = _error_result(
                future_to_key[future], "This expert took too long to respond. Please try again."
            )
            responses.append(result)
            yield "expert", result

        # Don't block the response on experts that timed out.
        executor.shutdown(wait=False, cancel_futures=True)

    # Restore original order
    order = {key: i for i, key in enumerate(unique_keys)}
    responses.sort(key=lambda r: order.get(r["expert_key"], 999))

    successful = [r for r in responses if r["status"] == "success"]
    failed     = [r for r in responses if r["status"] != "success"]

    synthesis, synthesis_error = (None, None)
    if len(successful) >= 2:
        synthesis, synthesis_error = synthesize(problem, successful)
        yield "synthesis", {"synthesis": synthesis, "synthesis_error": synthesis_error}

    yield "done", {
        "responses":        responses,
        "synthesis":        synthesis,
        "synthesis_error":  synthesis_error,
        "successful_count": len(successful),
        "failed_count":     len(failed),
    }


def run_panel(
    expert_keys: list[str],
    problem:     str,
    context:     str = "",
) -> dict[str, Any]:
    """
    Run a parallel multi-expert consultation.

    Parameters
    ----------
    expert_keys : list of backend expert keys, e.g. ["Software Architect", "Security Expert"]
    problem     : the user's problem description
    context     : optional additional context

    Returns
    -------
    {
        "responses": [...],     # list of per-expert result dicts
        "synthesis": {...},     # combined recommendation (or None if synthesis failed)
        "synthesis_error": "..." | None,
        "successful_count": N,
        "failed_count": N,
    }
    """
    result = None
    for event, payload in iter_panel(expert_keys, problem, context):
        if event == "done":
            result = payload
    return result
