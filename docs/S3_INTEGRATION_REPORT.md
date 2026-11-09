# S3 Integration Technical Report

## Overview

ExpertOS implements pluggable file storage through a backend abstraction layer. When `STORAGE_BACKEND=s3`, uploaded documents are stored in a private Amazon S3 bucket with SSE-S3 encryption instead of the local filesystem. Local storage remains the default and requires no configuration change.

## Architecture

```
HTTP POST /files
    │
    ▼
services/files.py       ← validates, extracts text, generates storage_name (UUID hex)
    │
    ▼
services/storage.py     ← get_storage() returns LocalStorage or S3Storage
    │
    ├── LocalStorage    ← writes to backend/data/uploads/
    └── S3Storage       ← puts object in S3 bucket (SSE-S3, private)
```

The `storage_name` (a random UUID hex string) is stored in the `uploaded_files` database table. It is the key used to read, update, or delete the object, and is never exposed to the browser.

## Implementation Details

### `backend/services/storage.py` (new file)

Contains three components:

1. **`LocalStorage`** — reads and writes files on the local filesystem under `backend/data/uploads/`. This was the only storage path before the integration.

2. **`S3Storage`** — stores files in an S3 bucket. Four operations:
   - `write(storage_name, data)` — `PutObject` with `ServerSideEncryption=AES256`
   - `read(storage_name)` → `bytes` — `GetObject`; raises `Forbidden` on `NoSuchKey`
   - `delete(storage_name)` — `DeleteObject`; raises on unexpected errors
   - `delete_many(storage_names)` — `DeleteObjects` (batch); best-effort, does not raise

3. **`get_storage()`** — factory function called once per request. Returns `S3Storage` when `STORAGE_BACKEND=s3` (and raises `RuntimeError` if `S3_BUCKET_NAME` is not set), otherwise returns `LocalStorage`.

boto3 resolves AWS credentials from environment variables, `~/.aws/credentials`, or EC2 instance metadata automatically — no credential logic is in the application code.

### `backend/services/files.py` (modified)

Four call sites replaced with `get_storage()` calls:

| Operation | Before | After |
|---|---|---|
| Save upload | `Path(uploads_dir() / storage_name).write_bytes(data)` | `get_storage().write(storage_name, data)` |
| Read image | `Path(uploads_dir() / row["storage_name"]).read_bytes()` | `get_storage().read(row["storage_name"])` |
| Delete single file | `Path(uploads_dir() / row["storage_name"]).unlink(missing_ok=True)` | `get_storage().delete(row["storage_name"])` |
| Delete many files | Loop of `unlink` calls | `get_storage().delete_many([...])` |

The `uploads_dir()` helper remains for backward compatibility (and is still used by `LocalStorage` internally).

### `backend/config.py` (modified)

Added three config values read at startup:
```python
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
AWS_REGION      = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME  = os.getenv("S3_BUCKET_NAME", "")
```

### `backend/requirements.txt` (modified)

Added: `boto3==1.38.23`

### `backend/.env.example` (modified)

Added the S3 section with `STORAGE_BACKEND`, `S3_BUCKET_NAME`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.

## Files Modified/Created

| File | Change |
|---|---|
| `backend/services/storage.py` | **New** — `LocalStorage`, `S3Storage`, `get_storage()` |
| `backend/services/files.py` | **Modified** — 4 storage call sites use `get_storage()` |
| `backend/config.py` | **Modified** — added S3 env var reads |
| `backend/requirements.txt` | **Modified** — added `boto3==1.38.23` |
| `backend/.env.example` | **Modified** — added S3 config section |
| `backend/tests/test_s3_storage.py` | **New** — 31 mocked S3 tests |

## Security Considerations

| Concern | Approach |
|---|---|
| Object privacy | No public bucket policy; all objects use default private ACL |
| Encryption at rest | `ServerSideEncryption=AES256` (SSE-S3) on every `PutObject` |
| Object key design | UUID hex — not guessable, not derived from filename |
| Credential exposure | boto3 reads credentials from env/IAM; never logged or sent to browser |
| Authorization | Existing `owner.owns(row)` check in `files.py` — unchanged |
| S3 failures | Never silently fall back to local; errors propagate to the caller |

## Test Coverage

All S3 tests use `unittest.mock.patch` to mock `boto3.client` — no real AWS credentials required.

| Test class | What it covers |
|---|---|
| `TestLocalStorageWrite` | Write and read roundtrip (local) |
| `TestLocalStorageDelete` | Delete and delete_many (local) |
| `TestLocalStorageRead` | Read missing file raises Forbidden |
| `TestS3StorageWrite` | PutObject called with AES256 encryption |
| `TestS3StorageRead` | GetObject returns correct bytes |
| `TestS3StorageReadMissing` | NoSuchKey raises Forbidden |
| `TestS3StorageReadError` | Other S3 errors raise Exception |
| `TestS3StorageDelete` | DeleteObject called correctly |
| `TestS3StorageDeleteMany` | DeleteObjects batch called |
| `TestGetStorageLocal` | Factory returns LocalStorage by default |
| `TestGetStorageS3` | Factory returns S3Storage when STORAGE_BACKEND=s3 |
| `TestGetStorageS3NoBucket` | RuntimeError when S3_BUCKET_NAME empty |
| + integration tests in test_api.py | Upload/retrieve/delete endpoints with mocked storage |

**Total: 228 tests, 0 failures.**

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `S3_BUCKET_NAME` | _(empty)_ | Required when `STORAGE_BACKEND=s3` |
| `AWS_REGION` | `us-east-1` | AWS region where the bucket lives |
| `AWS_ACCESS_KEY_ID` | _(empty)_ | IAM access key for local dev |
| `AWS_SECRET_ACCESS_KEY` | _(empty)_ | IAM secret key for local dev |

## Backward Compatibility

- `STORAGE_BACKEND` defaults to `local` — no configuration change needed for existing deployments.
- Existing locally-stored files are not migrated or touched.
- The `uploads_dir()` helper and local paths are unchanged.
- All existing API contracts, database schema, and expert behavior are preserved.
