"""Durable artifact storage shared by workers and the authenticated REST gateway."""

from __future__ import annotations

import os
from typing import Any


def _settings() -> dict[str, str]:
    return {
        "bucket": os.environ.get("ITHACA_ARTIFACT_BUCKET", "").strip(),
        "endpoint_url": os.environ.get("ITHACA_ARTIFACT_ENDPOINT_URL", "").strip(),
        "region_name": os.environ.get("ITHACA_ARTIFACT_REGION", "").strip(),
        "access_key": os.environ.get("ITHACA_ARTIFACT_ACCESS_KEY_ID", "").strip(),
        "secret_key": os.environ.get("ITHACA_ARTIFACT_SECRET_ACCESS_KEY", "").strip(),
    }


def object_storage_configured() -> bool:
    settings = _settings()
    return bool(settings["bucket"] and settings["endpoint_url"])


def _client() -> Any:
    settings = _settings()
    if not object_storage_configured():
        raise RuntimeError("artifact object storage is not configured")
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - deployment packaging guard
        raise RuntimeError("boto3 is required for artifact object storage") from exc
    kwargs: dict[str, Any] = {
        "endpoint_url": settings["endpoint_url"],
        "region_name": settings["region_name"] or None,
    }
    if settings["access_key"]:
        kwargs["aws_access_key_id"] = settings["access_key"]
    if settings["secret_key"]:
        kwargs["aws_secret_access_key"] = settings["secret_key"]
    return boto3.client("s3", **kwargs)


def put_artifact(*, key: str, content: bytes, media_type: str, sha256: str) -> str:
    """Upload one immutable artifact and return its private s3:// URI."""
    settings = _settings()
    _client().put_object(
        Bucket=settings["bucket"],
        Key=key,
        Body=content,
        ContentType=media_type,
        Metadata={"sha256": sha256},
        ServerSideEncryption="AES256",
    )
    return f"s3://{settings['bucket']}/{key}"


def presign_artifact(uri: str, *, expires_seconds: int = 300) -> str:
    """Return a short-lived download URL for a private s3:// artifact URI."""
    if not uri.startswith("s3://"):
        raise ValueError("artifact is not stored in object storage")
    bucket_and_key = uri[5:]
    bucket, separator, key = bucket_and_key.partition("/")
    if not separator or not bucket or not key:
        raise ValueError("invalid artifact object URI")
    configured_bucket = _settings()["bucket"]
    if configured_bucket and bucket != configured_bucket:
        raise ValueError("artifact bucket does not match configured storage")
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=max(30, min(int(expires_seconds), 900)),
    )


def open_artifact(uri: str) -> tuple[Any, int | None, str | None]:
    """Open a private object for authenticated server-side streaming."""
    if not uri.startswith("s3://"):
        raise ValueError("artifact is not stored in object storage")
    bucket_and_key = uri[5:]
    bucket, separator, key = bucket_and_key.partition("/")
    if not separator or not bucket or not key:
        raise ValueError("invalid artifact object URI")
    configured_bucket = _settings()["bucket"]
    if configured_bucket and bucket != configured_bucket:
        raise ValueError("artifact bucket does not match configured storage")
    response = _client().get_object(Bucket=bucket, Key=key)
    return response["Body"], response.get("ContentLength"), response.get("ContentType")
