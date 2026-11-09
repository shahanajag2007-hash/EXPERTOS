"""
Imported first by every test module: points the app at a throwaway database
so tests never touch backend/data/expertos.db (which holds real statistics).
"""
import atexit
import os
import shutil
import sys
import tempfile
import time

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_tmpdir = tempfile.mkdtemp(prefix="expertos-tests-")
os.environ["EXPERTOS_DB_PATH"] = os.path.join(_tmpdir, "test.db")
atexit.register(shutil.rmtree, _tmpdir, ignore_errors=True)


def fresh_database():
    """Point the app at a new empty database (call from setUp)."""
    from services import db

    path = os.path.join(_tmpdir, f"expertos_test_{os.getpid()}_{int(time.monotonic() * 1e6)}.db")
    os.environ["EXPERTOS_DB_PATH"] = path
    db.reset_for_tests()
    db.init_db()
    return path


# Browsers send a random client ID with every request (see services/auth.py).
TEST_CLIENT_ID = "test-browser-0123456789abcdef"


def client(app, client_id=TEST_CLIENT_ID):
    """A Flask test client that identifies itself like the ExpertOS frontend."""
    test_client = app.test_client()
    if client_id:
        test_client.environ_base["HTTP_X_CLIENT_ID"] = client_id
    return test_client
