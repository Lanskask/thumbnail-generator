"""
Thin client for driving the deployed thumbnail pipeline exactly the way the
frontend does: request a signed upload URL, PUT bytes to it, then poll for
a signed download URL until the thumbnail exists (or a timeout elapses).

Mirrors functions/get_upload_url/main.py's contract exactly:
  POST ?action=upload   {"filename", "contentType"} -> {"uploadUrl", "objectName"}
  GET  ?action=download ?objectName=...              -> {"exists", "downloadUrl"?}
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

DEFAULT_POLL_INTERVAL_SECONDS: float = 2.0
DEFAULT_POLL_TIMEOUT_SECONDS: float = 90.0
REQUEST_TIMEOUT_SECONDS: float = 30.0


class PipelineError(RuntimeError):
    """Raised when the deployed pipeline returns an unexpected response."""


class ThumbnailTimeoutError(PipelineError):
    """Raised when the thumbnail doesn't appear within the polling window."""


@dataclass(frozen=True)
class UploadHandle:
    """What `request_upload_url` needs to hand back for later polling."""

    object_name: str
    upload_url: str


def request_upload_url(function_url: str, *, filename: str, content_type: str) -> UploadHandle:
    """Call ?action=upload and return the signed PUT URL + object name."""
    response = requests.post(
        function_url,
        params={"action": "upload"},
        json={"filename": filename, "contentType": content_type},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise PipelineError(
            f"get-upload-url ?action=upload failed: {response.status_code} {response.text}"
        )

    body = response.json()
    if "uploadUrl" not in body or "objectName" not in body:
        raise PipelineError(f"unexpected upload response shape: {body}")

    return UploadHandle(object_name=body["objectName"], upload_url=body["uploadUrl"])


def put_image_bytes(upload_url: str, *, data: bytes, content_type: str) -> None:
    """PUT the raw image bytes to the signed URL, exactly as the browser would."""
    response = requests.put(
        upload_url,
        data=data,
        headers={"Content-Type": content_type},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code not in (200, 201):
        raise PipelineError(f"signed PUT upload failed: {response.status_code} {response.text}")


def poll_for_download_url(
    function_url: str,
    *,
    object_name: str,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_POLL_TIMEOUT_SECONDS,
) -> str:
    """Poll ?action=download until the thumbnail exists; return its download URL.

    Raises ThumbnailTimeoutError if it never appears within timeout_seconds —
    this is the main signal for "the Eventarc trigger / make-thumbnail
    function isn't firing".
    """
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        response = requests.get(
            function_url,
            params={"action": "download", "objectName": object_name},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise PipelineError(
                f"get-upload-url ?action=download failed: "
                f"{response.status_code} {response.text}"
            )

        body = response.json()
        if body.get("exists"):
            download_url = body.get("downloadUrl")
            if not download_url:
                raise PipelineError(f"exists=true but no downloadUrl: {body}")
            return download_url

        time.sleep(poll_interval_seconds)

    raise ThumbnailTimeoutError(
        f"thumbnail for {object_name!r} did not appear within "
        f"{timeout_seconds}s — check the make-thumbnail function logs "
        f"and the Eventarc trigger"
    )


def download_bytes(url: str) -> bytes:
    """GET raw bytes from a signed download URL."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise PipelineError(f"downloading thumbnail failed: {response.status_code} {response.text}")
    return response.content
