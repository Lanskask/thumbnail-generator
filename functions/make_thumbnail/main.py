"""
Cloud Function (2nd gen): auto-generate thumbnails for images uploaded to a
Cloud Storage bucket.

Trigger:  google.cloud.storage.object.v1.finalized on the SOURCE bucket
Action:   read the uploaded image, resize to a 200x200 thumbnail (preserving
          aspect ratio), write it to the DEST bucket.

Stays within GCP's Always Free tier as long as usage is light:
  - Cloud Functions:  2,000,000 invocations/month free
  - Cloud Storage:    5 GB-months free (regional, US regions)
  - Network egress:   5 GB/month free (excl. China/Australia)
"""

from __future__ import annotations

import io
import os
from typing import Final

import functions_framework
from cloudevents.http import CloudEvent
from google.cloud import storage
from google.cloud.storage import Blob, Bucket, Client
from PIL import Image
from PIL.Image import Image as PILImage

THUMBNAIL_SIZE: Final[tuple[int, int]] = (200, 200)
DEST_BUCKET: Final[str | None] = os.environ.get("DEST_BUCKET")
SUPPORTED_EXTENSIONS: Final[tuple[str, ...]] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
)
THUMBNAIL_PREFIX: Final[str] = "thumb_"

storage_client: Client = storage.Client()


def _is_processable(file_name: str) -> bool:
    if file_name.startswith(THUMBNAIL_PREFIX):
        return False
    return file_name.lower().endswith(SUPPORTED_EXTENSIONS)


def _build_thumbnail(image_bytes: bytes) -> tuple[bytes, str]:
    """Return (thumbnail_bytes, image_format) for the given source image bytes."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        img_typed: PILImage = img
        img_typed.thumbnail(THUMBNAIL_SIZE)
        output_buffer = io.BytesIO()
        img_format: str = img_typed.format or "PNG"
        img_typed.save(output_buffer, format=img_format)
        output_buffer.seek(0)
        return output_buffer.read(), img_format


@functions_framework.cloud_event
def make_thumbnail(cloud_event: CloudEvent) -> None:
    data: dict[str, str] = cloud_event.data

    bucket_name: str = data["bucket"]
    file_name: str = data["name"]

    if not _is_processable(file_name):
        print(f"Skipping non-processable file: {file_name}")
        return

    if not DEST_BUCKET:
        raise RuntimeError("DEST_BUCKET environment variable is not set")

    source_bucket: Bucket = storage_client.bucket(bucket_name)
    source_blob: Blob = source_bucket.blob(file_name)

    image_bytes: bytes = source_blob.download_as_bytes()
    thumbnail_bytes, _img_format = _build_thumbnail(image_bytes)

    dest_bucket: Bucket = storage_client.bucket(DEST_BUCKET)
    dest_blob: Blob = dest_bucket.blob(f"{THUMBNAIL_PREFIX}{file_name}")
    dest_blob.upload_from_string(
        thumbnail_bytes,
        content_type=source_blob.content_type or "application/octet-stream",
    )

    print(f"Created thumbnail {THUMBNAIL_PREFIX}{file_name} in gs://{DEST_BUCKET}")
