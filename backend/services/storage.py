"""
Storage backend abstraction for uploaded files.

Two backends:
  local  — writes files to the local filesystem (default)
  s3     — private AWS S3 bucket with SSE-S3 encryption

Select backend with STORAGE_BACKEND env var (default: "local").
get_storage() is called once per request so env var switches work in tests.
"""
import os
from pathlib import Path

import boto3
import botocore.exceptions

from services import db
from services.consultations import Forbidden


def _uploads_dir() -> Path:
    """Return (and create) the local upload directory. Mirrors files.uploads_dir()."""
    path = Path(os.getenv("EXPERTOS_UPLOAD_DIR") or (db.db_path().parent / "uploads"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class LocalStorage:
    """Stores files on the local filesystem."""

    def write(self, storage_name: str, data: bytes) -> None:
        (_uploads_dir() / storage_name).write_bytes(data)

    def read(self, storage_name: str) -> bytes:
        try:
            return (_uploads_dir() / storage_name).read_bytes()
        except OSError as exc:
            raise Forbidden(f"{storage_name} is no longer available.") from exc

    def delete(self, storage_name: str) -> None:
        (_uploads_dir() / storage_name).unlink(missing_ok=True)

    def delete_many(self, storage_names: list) -> None:
        for name in storage_names:
            self.delete(name)


class S3Storage:
    """Stores files in a private AWS S3 bucket with SSE-S3 encryption."""

    def __init__(self, bucket_name: str) -> None:
        self._bucket = bucket_name
        # boto3 reads credentials from env vars, ~/.aws/credentials, or IAM role automatically.
        self._s3 = boto3.client("s3")

    def write(self, storage_name: str, data: bytes) -> None:
        self._s3.put_object(
            Bucket=self._bucket,
            Key=storage_name,
            Body=data,
            ServerSideEncryption="AES256",
        )

    def read(self, storage_name: str) -> bytes:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=storage_name)
            return response["Body"].read()
        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "NoSuchKey":
                raise Forbidden("file no longer available") from exc
            print(f"[storage] S3 error reading object: {code}")
            raise Exception(f"S3 read failed ({code})") from exc

    def delete(self, storage_name: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=storage_name)
        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            print(f"[storage] S3 error deleting object: {code}")
            raise

    def delete_many(self, storage_names: list) -> None:
        if not storage_names:
            return
        objects = [{"Key": name} for name in storage_names]
        try:
            self._s3.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": objects, "Quiet": True},
            )
        except botocore.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            print(f"[storage] S3 error bulk-deleting objects: {code}")
            # deletion is best-effort cleanup — do not raise


def get_storage():
    """Return the configured storage backend. Called once per request."""
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "s3":
        bucket = os.getenv("S3_BUCKET_NAME", "")
        if not bucket:
            raise RuntimeError(
                "STORAGE_BACKEND=s3 requires S3_BUCKET_NAME to be set."
            )
        return S3Storage(bucket)
    return LocalStorage()
