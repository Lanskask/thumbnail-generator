"""
Cloud Function (2nd gen, HTTP): issues short-lived V4 signed URLs so the
browser can upload an image directly to the source bucket and poll for its
thumbnail in the destination bucket, without any credentials touching the
frontend and without proxying file bytes through a server.

Endpoints (single function, dispatched by `action` query param):
  POST /?action=upload  body: {"filename": "cat.jpg", "contentType": "image/jpeg"}
       -> {"uploadUrl": "...", "objectName": "1699999999-cat.jpg"}

  GET  /?action=download&objectName=thumb_1699999999-cat.jpg
       -> {"downloadUrl": "...", "exists": true|false}

CORS is restricted to the configured frontend origin via env var
ALLOWED_ORIGIN (falls back to "*" only if unset, for local testing).
"""

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import timedelta
from typing import Final

import functions_framework
import google.auth
import google.auth.transport.requests
from flask import Request, Response, jsonify
from google.auth.credentials import Credentials
from google.cloud import storage
from google.cloud.storage import Blob, Bucket, Client

SOURCE_BUCKET: Final[str | None] = os.environ.get("SOURCE_BUCKET")
DEST_BUCKET: Final[str | None] = os.environ.get("DEST_BUCKET")
ALLOWED_ORIGIN: Final[str] = os.environ.get("ALLOWED_ORIGIN", "*")
UPLOAD_URL_TTL: Final[timedelta] = timedelta(minutes=10)
DOWNLOAD_URL_TTL: Final[timedelta] = timedelta(minutes=10)
THUMBNAIL_PREFIX: Final[str] = "thumb_"

_SAFE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")
_ALLOWED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)

storage_client: Client = storage.Client()

# On Cloud Functions/Cloud Run, ADC resolves to compute_engine.Credentials,
# which carries only a bearer token (no private key). google-cloud-storage's
# V4 signing needs an actual key to sign with, so it can't do so directly
# from these credentials -- it must instead be told to sign via IAM's
# signBlob API, impersonating this function's own service account. That
# requires the service account to hold roles/iam.serviceAccountTokenCreator
# on itself (see terraform/iam.tf: upload_url_self_sign), and requires us to
# pass service_account_email + a fresh access_token to generate_signed_url()
# explicitly -- the client library will not infer this automatically.
#
# compute_engine.Credentials.service_account_email starts out as the literal
# placeholder string "default" -- it's only resolved to the real email as a
# side effect of calling refresh(), which fetches it from the metadata
# server. So the email must be read *after* refresh(), not cached at import
# time (that would freeze it at "default" and signBlob rejects that as an
# invalid account id).
# https://googleapis.dev/python/storage/latest/blobs.html#google.cloud.storage.blob.Blob.generate_signed_url
_SIGNING_CREDENTIALS: Credentials
_SIGNING_CREDENTIALS, _project = google.auth.default()


def _signing_kwargs() -> dict[str, object]:
    """Refresh the ADC token and return the extra kwargs V4 signing needs
    when running under compute-engine-style credentials (no private key)."""
    auth_request = google.auth.transport.requests.Request()
    _SIGNING_CREDENTIALS.refresh(auth_request)
    return {
        "service_account_email": getattr(_SIGNING_CREDENTIALS, "service_account_email", None),
        "access_token": _SIGNING_CREDENTIALS.token,
    }


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json_response(payload: dict[str, object], status: int = 200) -> Response:
    response: Response = jsonify(payload)
    response.status_code = status
    for key, value in _cors_headers().items():
        response.headers[key] = value
    return response


def _sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename)
    return _SAFE_NAME_RE.sub("_", base) or "upload"


def _handle_upload(request: Request) -> Response:
    if not SOURCE_BUCKET:
        return _json_response({"error": "SOURCE_BUCKET not configured"}, 500)

    body: dict[str, str] = request.get_json(silent=True) or {}
    filename: str = body.get("filename", "")
    content_type: str = body.get("contentType", "")

    if not filename:
        return _json_response({"error": "filename is required"}, 400)
    if content_type not in _ALLOWED_CONTENT_TYPES:
        return _json_response(
            {"error": f"contentType must be one of {sorted(_ALLOWED_CONTENT_TYPES)}"},
            400,
        )

    safe_name: str = _sanitize_filename(filename)
    object_name: str = f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}"

    bucket: Bucket = storage_client.bucket(SOURCE_BUCKET)
    blob: Blob = bucket.blob(object_name)

    upload_url: str = blob.generate_signed_url(
        version="v4",
        expiration=UPLOAD_URL_TTL,
        method="PUT",
        content_type=content_type,
        **_signing_kwargs(),
    )

    return _json_response({"uploadUrl": upload_url, "objectName": object_name})


def _handle_download(request: Request) -> Response:
    if not DEST_BUCKET:
        return _json_response({"error": "DEST_BUCKET not configured"}, 500)

    object_name: str = request.args.get("objectName", "")
    if not object_name:
        return _json_response({"error": "objectName is required"}, 400)

    thumb_object_name: str = f"{THUMBNAIL_PREFIX}{object_name}"
    bucket: Bucket = storage_client.bucket(DEST_BUCKET)
    blob: Blob = bucket.blob(thumb_object_name)

    if not blob.exists():
        return _json_response({"exists": False})

    download_url: str = blob.generate_signed_url(
        version="v4",
        expiration=DOWNLOAD_URL_TTL,
        method="GET",
        **_signing_kwargs(),
    )
    return _json_response({"exists": True, "downloadUrl": download_url})


@functions_framework.http
def get_upload_url(request: Request) -> Response:
    if request.method == "OPTIONS":
        response = Response("", status=204)
        for key, value in _cors_headers().items():
            response.headers[key] = value
        return response

    action: str = request.args.get("action", "")

    if action == "upload" and request.method == "POST":
        return _handle_upload(request)
    if action == "download" and request.method == "GET":
        return _handle_download(request)

    return _json_response({"error": "unknown action or wrong method"}, 400)
