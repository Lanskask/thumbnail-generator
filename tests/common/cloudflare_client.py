"""
HTTP helpers for the Cloudflare version of the pipeline (cloudflare/src/index.ts).

Same contract as the GCP function, with two differences the e2e test relies on:
  - `uploadUrl` / `downloadUrl` are *relative* ("/api/put/<name>", "/api/thumb/<name>"),
    so they are joined onto the base URL;
  - the PUT goes to the Worker itself, which resizes in that request, so the thumbnail
    exists as soon as the PUT returns (polling is kept as a safety net).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

ENV_CLOUDFLARE_URL: str = "CLOUDFLARE_URL"
REQUEST_TIMEOUT_SECONDS: float = 30.0
DEFAULT_POLL_TIMEOUT_SECONDS: float = 30.0
DEFAULT_POLL_INTERVAL_SECONDS: float = 0.5


class CloudflarePipelineError(RuntimeError):
    """The Worker answered, but not with what the contract promises."""


@dataclass(frozen=True)
class CloudflareUpload:
    object_name: str
    upload_url: str  # absolute


def load_base_url() -> str | None:
    """Base URL of the deployed Worker from $CLOUDFLARE_URL (no trailing slash), or None."""
    value = os.environ.get(ENV_CLOUDFLARE_URL, "").strip().rstrip("/")
    return value or None


def request_upload(base_url: str, *, filename: str, content_type: str) -> CloudflareUpload:
    response = requests.post(
        f"{base_url}/api",
        params={"action": "upload"},
        json={"filename": filename, "contentType": content_type},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise CloudflarePipelineError(
            f"?action=upload failed: {response.status_code} {response.text}"
        )
    body = response.json()
    if "uploadUrl" not in body or "objectName" not in body:
        raise CloudflarePipelineError(f"unexpected upload response shape: {body}")
    return CloudflareUpload(
        object_name=str(body["objectName"]), upload_url=f"{base_url}{body['uploadUrl']}"
    )


def put_image(upload_url: str, *, data: bytes, content_type: str) -> requests.Response:
    """PUT the bytes and return the raw response so callers can assert on error statuses too."""
    return requests.put(
        upload_url,
        data=data,
        headers={"Content-Type": content_type},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def fetch_thumbnail(
    base_url: str,
    *,
    object_name: str,
    timeout_seconds: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> bytes:
    """Poll ?action=download until the thumbnail exists, then download and return its bytes."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        response = requests.get(
            f"{base_url}/api",
            params={"action": "download", "objectName": object_name},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise CloudflarePipelineError(
                f"?action=download failed: {response.status_code} {response.text}"
            )
        body = response.json()
        if body.get("exists"):
            download = requests.get(
                f"{base_url}{body['downloadUrl']}", timeout=REQUEST_TIMEOUT_SECONDS
            )
            if download.status_code != 200:
                raise CloudflarePipelineError(
                    f"thumbnail download failed: {download.status_code} {download.text}"
                )
            return download.content
        if time.monotonic() >= deadline:
            raise CloudflarePipelineError(
                f"thumbnail for {object_name!r} did not appear within {timeout_seconds}s"
            )
        time.sleep(poll_interval_seconds)
