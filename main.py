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

import io
import os

import functions_framework
from cloudevents.http import CloudEvent
from google.cloud import storage
from PIL import Image

THUMBNAIL_SIZE = (200, 200)
DEST_BUCKET = os.environ.get("DEST_BUCKET")  # set via function deploy --set-env-vars
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

storage_client = storage.Client()


@functions_framework.cloud_event
def make_thumbnail(cloud_event: CloudEvent) -> None:
    data = cloud_event.data

    bucket_name = data["bucket"]
    file_name = data["name"]

    if not file_name.lower().endswith(SUPPORTED_EXTENSIONS):
        print(f"Skipping non-image file: {file_name}")
        return

    if file_name.startswith("thumb_"):
        print(f"Skipping already-processed file: {file_name}")
        return

    if not DEST_BUCKET:
        raise RuntimeError("DEST_BUCKET environment variable is not set")

    source_bucket = storage_client.bucket(bucket_name)
    source_blob = source_bucket.blob(file_name)

    image_bytes = source_blob.download_as_bytes()

    with Image.open(io.BytesIO(image_bytes)) as img:
        img.thumbnail(THUMBNAIL_SIZE)
        output_buffer = io.BytesIO()
        img_format = img.format or "PNG"
        img.save(output_buffer, format=img_format)
        output_buffer.seek(0)

    dest_bucket = storage_client.bucket(DEST_BUCKET)
    dest_blob = dest_bucket.blob(f"thumb_{file_name}")
    dest_blob.upload_from_file(output_buffer, content_type=source_blob.content_type)

    print(f"Created thumbnail thumb_{file_name} in gs://{DEST_BUCKET}")
