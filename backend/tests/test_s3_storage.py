"""
Tests for the storage abstraction (services/storage.py) and its integration
with services/files.py.

All S3 calls are mocked via unittest.mock.patch — no real AWS credentials
or bucket is required to run these tests.

Run from the backend directory:
    python -m pytest tests/test_s3_storage.py -v
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

import _testenv  # noqa: F401  (must come before app imports)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import botocore.exceptions


def _make_client_error(code: str) -> botocore.exceptions.ClientError:
    """Build a ClientError with the given error code."""
    return botocore.exceptions.ClientError(
        {"Error": {"Code": code, "Message": code}}, "operation"
    )


# ─── LocalStorage ─────────────────────────────────────────────────────────────

class LocalStorageTests(unittest.TestCase):
    """LocalStorage reads/writes/deletes files in the local uploads directory."""

    def setUp(self):
        _testenv.fresh_database()
        self.tmp = tempfile.mkdtemp()
        self.env_patcher = mock.patch.dict(os.environ, {"EXPERTOS_UPLOAD_DIR": self.tmp})
        self.env_patcher.start()
        from services.storage import LocalStorage
        self.storage = LocalStorage()

    def tearDown(self):
        self.env_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_creates_file(self):
        self.storage.write("abc123", b"hello world")
        path = os.path.join(self.tmp, "abc123")
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"hello world")

    def test_read_returns_bytes(self):
        self.storage.write("myfile", b"test data")
        result = self.storage.read("myfile")
        self.assertEqual(result, b"test data")

    def test_read_missing_raises_forbidden(self):
        from services.consultations import Forbidden
        with self.assertRaises(Forbidden):
            self.storage.read("does-not-exist")

    def test_delete_removes_file(self):
        self.storage.write("todelete", b"data")
        self.storage.delete("todelete")
        path = os.path.join(self.tmp, "todelete")
        self.assertFalse(os.path.exists(path))

    def test_delete_missing_is_silent(self):
        # Should not raise
        self.storage.delete("nonexistent")

    def test_delete_many_removes_all(self):
        self.storage.write("f1", b"a")
        self.storage.write("f2", b"b")
        self.storage.delete_many(["f1", "f2"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "f1")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "f2")))


# ─── S3Storage write ──────────────────────────────────────────────────────────

class S3StorageWriteTests(unittest.TestCase):
    """S3Storage.write calls put_object with SSE-S3 encryption."""

    def setUp(self):
        self.boto_patcher = mock.patch("boto3.client")
        self.mock_boto_client = self.boto_patcher.start()
        self.mock_s3 = mock.MagicMock()
        self.mock_boto_client.return_value = self.mock_s3
        from services.storage import S3Storage
        self.storage = S3Storage("my-test-bucket")

    def tearDown(self):
        self.boto_patcher.stop()

    def test_write_calls_put_object(self):
        self.storage.write("key123", b"file content")
        self.mock_s3.put_object.assert_called_once_with(
            Bucket="my-test-bucket",
            Key="key123",
            Body=b"file content",
            ServerSideEncryption="AES256",
        )

    def test_write_uses_sse_s3_encryption(self):
        self.storage.write("anykey", b"data")
        call_kwargs = self.mock_s3.put_object.call_args.kwargs
        self.assertEqual(call_kwargs["ServerSideEncryption"], "AES256")

    def test_write_propagates_client_error(self):
        self.mock_s3.put_object.side_effect = _make_client_error("AccessDenied")
        with self.assertRaises(botocore.exceptions.ClientError):
            self.storage.write("key", b"data")


# ─── S3Storage read ───────────────────────────────────────────────────────────

class S3StorageReadTests(unittest.TestCase):
    """S3Storage.read returns bytes; NoSuchKey → Forbidden; other errors → Exception."""

    def setUp(self):
        self.boto_patcher = mock.patch("boto3.client")
        self.mock_boto_client = self.boto_patcher.start()
        self.mock_s3 = mock.MagicMock()
        self.mock_boto_client.return_value = self.mock_s3
        from services.storage import S3Storage
        self.storage = S3Storage("my-test-bucket")

    def tearDown(self):
        self.boto_patcher.stop()

    def test_read_returns_bytes(self):
        body_mock = mock.MagicMock()
        body_mock.read.return_value = b"s3 content"
        self.mock_s3.get_object.return_value = {"Body": body_mock}
        result = self.storage.read("some-key")
        self.assertEqual(result, b"s3 content")

    def test_read_calls_get_object_with_correct_args(self):
        body_mock = mock.MagicMock()
        body_mock.read.return_value = b""
        self.mock_s3.get_object.return_value = {"Body": body_mock}
        self.storage.read("my-key")
        self.mock_s3.get_object.assert_called_once_with(
            Bucket="my-test-bucket", Key="my-key"
        )

    def test_no_such_key_raises_forbidden(self):
        from services.consultations import Forbidden
        self.mock_s3.get_object.side_effect = _make_client_error("NoSuchKey")
        with self.assertRaises(Forbidden):
            self.storage.read("missing-key")

    def test_other_client_error_raises_exception(self):
        self.mock_s3.get_object.side_effect = _make_client_error("AccessDenied")
        with self.assertRaises(Exception):
            self.storage.read("key")

    def test_other_client_error_logs_message(self):
        self.mock_s3.get_object.side_effect = _make_client_error("InternalError")
        with mock.patch("builtins.print") as mock_print:
            with self.assertRaises(Exception):
                self.storage.read("key")
            mock_print.assert_called()


# ─── S3Storage delete ─────────────────────────────────────────────────────────

class S3StorageDeleteTests(unittest.TestCase):
    """S3Storage.delete calls delete_object; errors are logged and re-raised."""

    def setUp(self):
        self.boto_patcher = mock.patch("boto3.client")
        self.mock_boto_client = self.boto_patcher.start()
        self.mock_s3 = mock.MagicMock()
        self.mock_boto_client.return_value = self.mock_s3
        from services.storage import S3Storage
        self.storage = S3Storage("my-test-bucket")

    def tearDown(self):
        self.boto_patcher.stop()

    def test_delete_calls_delete_object(self):
        self.storage.delete("del-key")
        self.mock_s3.delete_object.assert_called_once_with(
            Bucket="my-test-bucket", Key="del-key"
        )

    def test_delete_error_is_reraised(self):
        self.mock_s3.delete_object.side_effect = _make_client_error("AccessDenied")
        with self.assertRaises(botocore.exceptions.ClientError):
            self.storage.delete("key")

    def test_delete_error_is_logged(self):
        self.mock_s3.delete_object.side_effect = _make_client_error("AccessDenied")
        with mock.patch("builtins.print") as mock_print:
            with self.assertRaises(Exception):
                self.storage.delete("key")
            mock_print.assert_called()


# ─── S3Storage delete_many ────────────────────────────────────────────────────

class S3StorageDeleteManyTests(unittest.TestCase):
    """S3Storage.delete_many uses the bulk delete_objects API."""

    def setUp(self):
        self.boto_patcher = mock.patch("boto3.client")
        self.mock_boto_client = self.boto_patcher.start()
        self.mock_s3 = mock.MagicMock()
        self.mock_boto_client.return_value = self.mock_s3
        from services.storage import S3Storage
        self.storage = S3Storage("my-test-bucket")

    def tearDown(self):
        self.boto_patcher.stop()

    def test_delete_many_uses_bulk_api(self):
        self.storage.delete_many(["k1", "k2", "k3"])
        self.mock_s3.delete_objects.assert_called_once_with(
            Bucket="my-test-bucket",
            Delete={"Objects": [{"Key": "k1"}, {"Key": "k2"}, {"Key": "k3"}], "Quiet": True},
        )

    def test_delete_many_empty_list_is_noop(self):
        self.storage.delete_many([])
        self.mock_s3.delete_objects.assert_not_called()

    def test_delete_many_error_is_not_raised(self):
        self.mock_s3.delete_objects.side_effect = _make_client_error("AccessDenied")
        # Should not raise — deletion is best-effort
        self.storage.delete_many(["k1", "k2"])

    def test_delete_many_error_is_logged(self):
        self.mock_s3.delete_objects.side_effect = _make_client_error("AccessDenied")
        with mock.patch("builtins.print") as mock_print:
            self.storage.delete_many(["k1"])
            mock_print.assert_called()


# ─── get_storage factory ──────────────────────────────────────────────────────

class GetStorageFactoryTests(unittest.TestCase):
    """get_storage() returns the correct backend based on STORAGE_BACKEND env var."""

    def test_local_is_default(self):
        env = dict(os.environ)
        env.pop("STORAGE_BACKEND", None)
        with mock.patch.dict(os.environ, env, clear=True):
            from services.storage import get_storage, LocalStorage
            result = get_storage()
            self.assertIsInstance(result, LocalStorage)

    def test_local_backend_returns_local_storage(self):
        with mock.patch.dict(os.environ, {"STORAGE_BACKEND": "local"}):
            from services.storage import get_storage, LocalStorage
            result = get_storage()
            self.assertIsInstance(result, LocalStorage)

    def test_s3_backend_returns_s3_storage(self):
        with mock.patch.dict(os.environ, {"STORAGE_BACKEND": "s3", "S3_BUCKET_NAME": "my-bucket"}):
            with mock.patch("boto3.client"):
                from services.storage import get_storage, S3Storage
                result = get_storage()
                self.assertIsInstance(result, S3Storage)

    def test_s3_without_bucket_name_raises_runtime_error(self):
        env = dict(os.environ)
        env["STORAGE_BACKEND"] = "s3"
        env.pop("S3_BUCKET_NAME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            from services.storage import get_storage
            with self.assertRaises(RuntimeError):
                get_storage()

    def test_unknown_backend_returns_local_storage(self):
        with mock.patch.dict(os.environ, {"STORAGE_BACKEND": "invalid-backend"}):
            from services.storage import get_storage, LocalStorage
            result = get_storage()
            self.assertIsInstance(result, LocalStorage)


# ─── files.py integration (local mode) ───────────────────────────────────────

class FilesIntegrationTests(unittest.TestCase):
    """Verify files.py storage operations work end-to-end in local mode."""

    def setUp(self):
        _testenv.fresh_database()
        self.tmp = tempfile.mkdtemp()
        self.env_patcher = mock.patch.dict(
            os.environ,
            {"EXPERTOS_UPLOAD_DIR": self.tmp, "STORAGE_BACKEND": "local"},
        )
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_owner(self):
        """Create a minimal owner object matching the auth.Owner interface."""
        class FakeOwner:
            user_id = None
            client_hash = "aabbccdd" * 4  # 32 hex chars

            def columns(self):
                return (None, self.client_hash)

            def owns(self, row):
                return row["client_hash"] == self.client_hash
        return FakeOwner()

    def test_save_upload_writes_file(self):
        """save_upload stores the file and returns metadata."""
        from services.files import save_upload
        owner = self._make_owner()
        result = save_upload(owner, "test.txt", b"hello world")
        self.assertEqual(result["filename"], "test.txt")
        self.assertEqual(result["kind"], "document")
        # File should exist in uploads dir
        from services.files import uploads_dir
        storage_files = list(uploads_dir().iterdir())
        self.assertEqual(len(storage_files), 1)

    def test_delete_removes_file(self):
        """delete() removes the file from storage."""
        from services.files import save_upload, delete
        from services.files import uploads_dir
        owner = self._make_owner()
        result = save_upload(owner, "todelete.txt", b"data")
        file_id = result["id"]
        delete(owner, file_id)
        storage_files = list(uploads_dir().iterdir())
        self.assertEqual(len(storage_files), 0)

    def test_image_bytes_returns_content(self):
        """image_bytes() returns the raw file bytes."""
        from services.files import save_upload, image_bytes
        from services import db
        # PNG magic bytes
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        owner = self._make_owner()
        result = save_upload(owner, "img.png", png_data)
        with db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM uploaded_files WHERE id = ?", (result["id"],)
            ).fetchone()
        data = image_bytes(row)
        self.assertEqual(data, png_data)


# ─── S3 failure handling ──────────────────────────────────────────────────────

class S3FailureTests(unittest.TestCase):
    """S3 write failures propagate as errors and do not silently fall back to local."""

    def setUp(self):
        _testenv.fresh_database()
        self.tmp = tempfile.mkdtemp()
        self.env_patcher = mock.patch.dict(
            os.environ,
            {"EXPERTOS_UPLOAD_DIR": self.tmp, "STORAGE_BACKEND": "s3", "S3_BUCKET_NAME": "fail-bucket"},
        )
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_owner(self, suffix="ccddeeaa"):
        owner_class = type("Owner", (), {
            "user_id": None,
            "client_hash": suffix * 4,
            "columns": lambda self: (None, self.client_hash),
            "owns": lambda self, row: row["client_hash"] == self.client_hash,
        })
        return owner_class()

    def test_s3_write_failure_propagates_does_not_fall_back(self):
        """An S3 put_object failure raises an error, not a silent local write."""
        from services.files import save_upload
        owner = self._make_owner()
        with mock.patch("boto3.client") as mock_boto:
            mock_s3 = mock.MagicMock()
            mock_boto.return_value = mock_s3
            mock_s3.put_object.side_effect = _make_client_error("AccessDenied")
            with self.assertRaises(Exception):
                save_upload(owner, "fail.txt", b"should not be saved")
        # Nothing should have been written to local disk
        from services.files import uploads_dir
        storage_files = list(uploads_dir().iterdir())
        self.assertEqual(len(storage_files), 0)

    def test_s3_write_failure_rolls_back_db(self):
        """When S3 write fails, no DB record is created."""
        from services.files import save_upload
        from services import db
        owner = self._make_owner(suffix="ffeeddcc")
        with mock.patch("boto3.client") as mock_boto:
            mock_s3 = mock.MagicMock()
            mock_boto.return_value = mock_s3
            mock_s3.put_object.side_effect = _make_client_error("AccessDenied")
            with self.assertRaises(Exception):
                save_upload(owner, "fail.txt", b"should not be saved")
        with db.connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM uploaded_files").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
