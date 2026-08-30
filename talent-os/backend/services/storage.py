"""
Talent OS — Object storage (Cloudflare R2, S3-compatible) for CV files.

CVs used to be written to /app/uploads/cv with plain open() — there's no
volume mount, so every deploy wiped them. This module puts them in R2
instead, addressed via routers/candidate.py's cv_file_path column (values
now look like "cv/{user_id}/{uuid4}.{ext}" rather than a local filename).

boto3/botocore are synchronous, so every network-touching function here has
an `_async` wrapper that runs the sync call in a thread via asyncio.to_thread
so the FastAPI event loop never blocks on it.

The app must keep booting when R2 isn't configured yet (empty env vars) —
is_configured() lets callers fall back to the legacy local-disk path instead
of erroring out.
"""
import asyncio
import logging
from typing import Optional

from core.config import settings

logger = logging.getLogger("talent_os.storage")

_client = None


def is_configured() -> bool:
    """True if all four R2 settings are present. Callers use this to decide
    whether to use R2 or fall back to legacy local-disk behavior."""
    return bool(
        settings.r2_endpoint
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
        and settings.r2_bucket
    )


def _get_client():
    """Lazily build (and cache) the boto3 S3 client for R2. Only called once
    is_configured() has been checked by the caller."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            # R2 wants the "auto" region and SigV4.
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )
    return _client


# ── Sync implementations (run off the event loop via asyncio.to_thread) ────

def _put_object_sync(key: str, data: bytes, content_type: str) -> None:
    client = _get_client()
    client.put_object(
        Bucket=settings.r2_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def _presigned_get_sync(key: str, ttl: int, filename: Optional[str]) -> str:
    client = _get_client()
    params = {"Bucket": settings.r2_bucket, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return client.generate_presigned_url(
        "get_object", Params=params, ExpiresIn=ttl,
    )


def _delete_object_sync(key: str) -> None:
    client = _get_client()
    # S3-style delete_object is idempotent by spec (204 whether or not the
    # key existed), but be defensive against providers that raise on a
    # missing key anyway.
    try:
        client.delete_object(Bucket=settings.r2_bucket, Key=key)
    except client.exceptions.ClientError as e:  # pragma: no cover - defensive
        code = e.response.get("Error", {}).get("Code", "")
        if code not in ("NoSuchKey", "404"):
            raise


def _object_exists_sync(key: str) -> bool:
    client = _get_client()
    from botocore.exceptions import ClientError

    try:
        client.head_object(Bucket=settings.r2_bucket, Key=key)
        return True
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def _delete_prefix_sync(prefix: str) -> list:
    """Delete every object under `prefix` (e.g. "cv/42/"). Paginated
    list_objects_v2 + batched delete_objects (max 1000 keys/call per the S3
    API). Idempotent: an empty/missing prefix deletes nothing and is not an
    error. Returns the list of keys actually deleted, so callers can log
    what happened -- used by GDPR erasure to cover pre-existing orphans
    (files left behind by an earlier upload that was never cleaned up)
    alongside whatever key is currently referenced in the DB."""
    client = _get_client()
    deleted = []
    continuation_token = None

    while True:
        kwargs = {"Bucket": settings.r2_bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = client.list_objects_v2(**kwargs)

        keys = [{"Key": obj["Key"]} for obj in resp.get("Contents", [])]
        for batch_start in range(0, len(keys), 1000):
            batch = keys[batch_start:batch_start + 1000]
            if not batch:
                continue
            del_resp = client.delete_objects(
                Bucket=settings.r2_bucket,
                Delete={"Objects": batch, "Quiet": True},
            )
            errors = del_resp.get("Errors") or []
            if errors:
                raise RuntimeError(
                    f"delete_objects failed for {len(errors)} key(s) under prefix "
                    f"{prefix!r}: {errors}"
                )
            deleted.extend(obj["Key"] for obj in batch)

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break

    return deleted


# ── Async wrappers used by routers ──────────────────────────────────────

async def put_object(key: str, data: bytes, content_type: str) -> None:
    await asyncio.to_thread(_put_object_sync, key, data, content_type)


async def presigned_get(key: str, ttl: int = 300, filename: Optional[str] = None) -> str:
    return await asyncio.to_thread(_presigned_get_sync, key, ttl, filename)


async def delete_object(key: str) -> None:
    """Idempotent: deleting a key that doesn't exist is not an error."""
    await asyncio.to_thread(_delete_object_sync, key)


async def object_exists(key: str) -> bool:
    return await asyncio.to_thread(_object_exists_sync, key)


async def delete_prefix(prefix: str) -> list:
    """Delete every object under `prefix`. Idempotent (a prefix with no
    objects deletes nothing). Returns the keys that were deleted."""
    return await asyncio.to_thread(_delete_prefix_sync, prefix)


# ── Pure helpers (no I/O — safe to unit test without a client) ─────────────

def cv_key(user_id: int, ext: str, file_id: str) -> str:
    """Build the R2 object key for a candidate's CV upload.

    ext should include the leading dot (e.g. ".pdf"); file_id is the caller's
    uuid4().hex so this stays a pure function for testing.
    """
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"cv/{user_id}/{file_id}{ext}"


def cv_prefix(user_id: int) -> str:
    """The R2 key prefix under which all of a user's CV uploads live (past
    and present) -- used by GDPR erasure to sweep up orphaned objects left
    behind by a re-upload that predates the delete-old-key fix, not just the
    single key currently referenced in the DB."""
    return f"cv/{user_id}/"


def is_r2_key(cv_file_path: Optional[str]) -> bool:
    """True if a stored cv_file_path value is an R2 object key rather than a
    legacy local-disk path. Factored out so both the branch logic and its
    unit tests can share it."""
    return bool(cv_file_path) and cv_file_path.startswith("cv/")


def should_delete_old_key(old_cv_file_path: Optional[str], new_key: str) -> bool:
    """True if a CV re-upload should best-effort delete the previously
    stored R2 object. Factored out of routers/candidate.py's upload_cv so
    the "when do we clean up the superseded object" decision is a plain,
    testable function: only an old value that is itself an R2 key (not a
    legacy local path, not empty) and actually different from the brand new
    key qualifies -- deleting a legacy local path here is never correct
    (that's local-disk cleanup, not R2), and a same-key no-op guards against
    the vanishingly unlikely uuid4 collision wiping the file just written."""
    return is_r2_key(old_cv_file_path) and old_cv_file_path != new_key
