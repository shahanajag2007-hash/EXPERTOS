"""
SQLite persistence for ExpertOS.

The database lives at EXPERTOS_DB_PATH (default backend/data/expertos.db) and
is created on first use. Schema changes are numbered SQL files in
backend/migrations/, applied once each in order and recorded in
schema_migrations, so any installation can be rebuilt reproducibly.

Each operation opens its own short-lived connection, which keeps the module
safe to use from Flask's request threads and the panel's worker threads.
"""
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BASE_DIR / "migrations"

_init_lock = threading.Lock()
_initialized_path = None


def db_path():
    return Path(os.getenv("EXPERTOS_DB_PATH") or BASE_DIR / "data" / "expertos.db")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class DatabaseError(Exception):
    """A storage operation failed. The message is safe to show to users."""

    status_code = 503


def _connect():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)  # autocommit; explicit BEGIN below
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    """Create the database and apply any pending migrations."""
    global _initialized_path

    with _init_lock:
        path = str(db_path())
        if _initialized_path == path:
            return

        conn = _connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}

            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if migration.stem in applied:
                    continue
                print(f"[db] Applying migration {migration.name}")
                # SQLite parses the script itself (comments, semicolons); the
                # migration and its version row commit together or not at all.
                version = migration.stem.replace("'", "''")
                script = (
                    "BEGIN;\n"
                    + migration.read_text(encoding="utf-8")
                    + f"\nINSERT INTO schema_migrations (version, applied_at)"
                      f" VALUES ('{version}', '{utc_now()}');\nCOMMIT;"
                )
                try:
                    conn.executescript(script)
                except Exception:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

        _initialized_path = path


@contextmanager
def connection(write=False):
    """
    Yield a connection. With write=True the block runs in one transaction
    (BEGIN IMMEDIATE, so concurrent writers queue instead of conflicting).
    sqlite3 errors are converted to DatabaseError.
    """
    try:
        init_db()
        conn = _connect()
    except (sqlite3.Error, OSError) as exc:
        print(f"[db] Could not open database: {exc}")
        raise DatabaseError("ExpertOS storage is unavailable right now. Please try again.") from exc

    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.execute("COMMIT")
    except sqlite3.IntegrityError:
        if write:
            conn.execute("ROLLBACK")
        raise
    except sqlite3.Error as exc:
        if write:
            conn.execute("ROLLBACK")
        print(f"[db] Database error: {exc}")
        raise DatabaseError("ExpertOS storage is unavailable right now. Please try again.") from exc
    except BaseException:
        if write and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def reset_for_tests():
    """Forget the initialised path so tests can point EXPERTOS_DB_PATH elsewhere."""
    global _initialized_path
    with _init_lock:
        _initialized_path = None
