"""
Print contact-form messages stored in the ExpertOS database (newest first).

    cd backend
    python scripts/list_contact_messages.py            # latest 20
    python scripts/list_contact_messages.py --all
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import db  # noqa: E402


def main():
    limit = "" if "--all" in sys.argv else "LIMIT 20"
    with db.connection() as conn:
        rows = conn.execute(f"SELECT * FROM contact_messages ORDER BY created_at DESC {limit}").fetchall()

    if not rows:
        print("No contact messages.")
        return

    for r in rows:
        print("=" * 70)
        print(f"#{r['id']}  {r['created_at']}")
        print(f"From:    {r['name'] or '(no name)'} <{r['email']}>")
        print(f"Subject: {r['subject']}")
        print()
        print(r["message"])
    print("=" * 70)
    print(f"{len(rows)} message(s). Messages are deleted automatically after the retention period.")


if __name__ == "__main__":
    main()
