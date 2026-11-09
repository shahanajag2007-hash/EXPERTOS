"""
What the AI is shown from a conversation and its attached files.

Long conversations: the most recent messages are included in full; earlier
ones are condensed (each shortened) newest-first within a character budget,
so the expert keeps the thread of a long discussion without the prompt
growing without bound. Anything left out is stated in the prompt, never
dropped silently.

Attached documents: their extracted text is included up to a budget shared
between the files; a file that doesn't fit completely is marked as cut, with
how much was included. Images are listed and passed to the AI separately.
"""

RECENT_MESSAGES = 12
RECENT_MESSAGE_CHARS = 4000
OLDER_MESSAGE_CHARS = 300
HISTORY_BUDGET_CHARS = 16_000

DOCUMENTS_BUDGET_CHARS = 40_000
MIN_DOCUMENT_SHARE = 4_000


def _speaker(item):
    if item.get("sender") == "user" or item.get("role") == "user":
        return "User"
    expert = item.get("expert")
    if isinstance(expert, dict) and expert.get("name"):
        return expert["name"]
    return item.get("speaker") or "Expert"


def _shorten(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_history(history):
    """Conversation text for the prompt from [{sender|role, message, expert?}]."""
    items = [
        item for item in history or []
        if isinstance(item, dict) and item.get("type", "chat") == "chat" and str(item.get("message", "")).strip()
    ]
    recent = items[-RECENT_MESSAGES:]
    older = items[:-RECENT_MESSAGES] if len(items) > RECENT_MESSAGES else []

    recent_lines = [f"{_speaker(i)}: {_shorten(i['message'], RECENT_MESSAGE_CHARS)}" for i in recent]
    budget = HISTORY_BUDGET_CHARS - sum(len(line) for line in recent_lines)

    older_lines = []
    for item in reversed(older):
        line = f"{_speaker(item)}: {_shorten(item['message'], OLDER_MESSAGE_CHARS)}"
        if budget - len(line) < 0:
            break
        budget -= len(line)
        older_lines.append(line)
    older_lines.reverse()

    omitted = len(older) - len(older_lines)
    parts = []
    if omitted:
        parts.append(f"[{omitted} earliest message(s) of this conversation are not shown.]")
    if older_lines:
        parts.append("Earlier in the conversation (condensed):\n" + "\n".join(older_lines))
        parts.append("Most recent messages:")
    parts.extend(recent_lines)
    return "\n".join(parts)


def documents_section(rows):
    """
    Prompt text for attached files (rows from uploaded_files), or "" if none.
    """
    if not rows:
        return ""

    documents = [r for r in rows if r["kind"] == "document"]
    images = [r for r in rows if r["kind"] == "image"]
    share = max(MIN_DOCUMENT_SHARE, DOCUMENTS_BUDGET_CHARS // max(1, len(documents)))
    remaining = DOCUMENTS_BUDGET_CHARS

    blocks = []
    for row in documents:
        text = (row["extracted_text"] or "").strip()
        header = f"--- FILE: {row['filename']} ---"
        notes = [row["extraction_note"]] if row["extraction_note"] else []
        if not text:
            blocks.append(f"{header}\n[No text could be extracted from this file"
                          f"{': ' + row['extraction_note'] if row['extraction_note'] else ''}.]")
            continue
        allowed = max(0, min(share, remaining))
        if allowed == 0:
            blocks.append(f"{header}\n[Not included: the attached files are too long to include all of them.]")
            continue
        if len(text) > allowed:
            notes.append(f"only the first {allowed:,} of {len(text):,} characters are included here")
            text = text[:allowed]
        remaining -= len(text)
        note_line = f"[Note: {'; '.join(notes)}.]\n" if notes else ""
        blocks.append(f"{header}\n{note_line}{text}")

    for number, row in enumerate(images, 1):
        blocks.append(f"--- IMAGE {number}: {row['filename']} (attached to this message as an image) ---")

    return (
        "ATTACHED FILES\n"
        "The user attached these files. Use their actual content when it is relevant. "
        "Quote or refer to them accurately, say which file you are referring to, and never claim "
        "a file says something it does not. If part of a file was not included, say so rather "
        "than guessing what it contains.\n\n"
        + "\n\n".join(blocks)
    )
