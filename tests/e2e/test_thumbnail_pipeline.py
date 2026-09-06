"""
End-to-end test against a *live* deployment of the thumbnail pipeline.

This exercises the exact same path the frontend takes:
  1. POST ?action=upload      -> signed PUT URL
  2. PUT image bytes          -> lands in the source bucket
  3. GCS finalize event fires -> Eventarc -> make-thumbnail function
  4. Poll ?action=download    -> signed GET URL once the thumbnail exists
  5. Download + assert it was actually resized to <= 200x200

Requires a real deployment: run `terraform apply` in terraform/ first (or
set THUMBNAILER_FUNCTION_URL / THUMBNAILER_SOURCE_BUCKET /
THUMBNAILER_DEST_BUCKET explicitly). This test makes real network calls and
real GCP API calls — it is not a unit test and is not run by default via
`make test-unit`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import requests
from google.cloud import storage

from tests.common.config import ConfigError, DeploymentConfig, load_deployment_config
from tests.common.images import GeneratedImage, make_test_image, read_image_dimensions
from tests.common.pipeline_client import (
    ThumbnailTimeoutError,
    UploadHandle,
    download_bytes,
    poll_for_download_url,
    put_image_bytes,
    request_upload_url,
)

THUMBNAIL_MAX_DIMENSION: int = 200


@pytest.fixture(scope="session")
def deployment_config() -> DeploymentConfig:
    try:
        return load_deployment_config()
    except ConfigError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def uploaded_object_cleanup(
    deployment_config: DeploymentConfig,
) -> Iterator[list[str]]:
    """Yield a list the test appends object names to; delete them afterward.

    Both the raw upload (source bucket) and its thumbnail (dest bucket,
    `thumb_` prefix) are cleaned up, so repeated test runs don't accumulate
    objects while waiting on the buckets' own 7-day lifecycle rule.
    """
    object_names: list[str] = []
    yield object_names

    client = storage.Client()
    source_bucket = client.bucket(deployment_config.source_bucket)
    dest_bucket = client.bucket(deployment_config.dest_bucket)

    for object_name in object_names:
        for bucket, name in (
            (source_bucket, object_name),
            (dest_bucket, f"thumb_{object_name}"),
        ):
            blob = bucket.blob(name)
            if blob.exists():
                blob.delete()


def _run_pipeline(
    deployment_config: DeploymentConfig,
    image: GeneratedImage,
    uploaded_object_cleanup: list[str],
) -> bytes:
    """Drive the full pipeline for one image and return the thumbnail bytes."""
    handle: UploadHandle = request_upload_url(
        deployment_config.function_url,
        filename=image.filename,
        content_type=image.content_type,
    )
    uploaded_object_cleanup.append(handle.object_name)

    put_image_bytes(handle.upload_url, data=image.data, content_type=image.content_type)

    download_url = poll_for_download_url(
        deployment_config.function_url,
        object_name=handle.object_name,
    )
    return download_bytes(download_url)


@pytest.mark.e2e
class TestThumbnailPipeline:
    def test_jpeg_upload_produces_resized_thumbnail(
        self,
        deployment_config: DeploymentConfig,
        uploaded_object_cleanup: list[str],
    ) -> None:
        image = make_test_image(
            width=800, height=600, content_type="image/jpeg", color=(200, 30, 30)
        )

        thumbnail_bytes = _run_pipeline(deployment_config, image, uploaded_object_cleanup)

        width, height = read_image_dimensions(thumbnail_bytes)
        assert width <= THUMBNAIL_MAX_DIMENSION
        assert height <= THUMBNAIL_MAX_DIMENSION
        # Original was landscape (800x600); aspect ratio should be preserved.
        assert width > height

    def test_png_upload_is_processed(
        self,
        deployment_config: DeploymentConfig,
        uploaded_object_cleanup: list[str],
    ) -> None:
        image = make_test_image(
            width=500, height=500, content_type="image/png", color=(30, 200, 30)
        )

        thumbnail_bytes = _run_pipeline(deployment_config, image, uploaded_object_cleanup)

        width, height = read_image_dimensions(thumbnail_bytes)
        assert width == THUMBNAIL_MAX_DIMENSION
        assert height == THUMBNAIL_MAX_DIMENSION

    def test_nonexistent_object_reports_not_exists(
        self, deployment_config: DeploymentConfig
    ) -> None:
        response = requests.get(
            deployment_config.function_url,
            params={"action": "download", "objectName": "does-not-exist.jpg"},
            timeout=30,
        )
        assert response.status_code == 200
        assert response.json() == {"exists": False}

    def test_thumbnail_never_appears_for_dropped_upload_times_out(
        self,
        deployment_config: DeploymentConfig,
        uploaded_object_cleanup: list[str],
    ) -> None:
        """Sanity check on the *test harness itself*: request an upload URL
        but never PUT any bytes to it. No GCS finalize event will ever fire,
        so polling must time out rather than hang or false-positive.
        """
        handle = request_upload_url(
            deployment_config.function_url,
            filename="never-uploaded.jpg",
            content_type="image/jpeg",
        )
        uploaded_object_cleanup.append(handle.object_name)

        with pytest.raises(ThumbnailTimeoutError):
            poll_for_download_url(
                deployment_config.function_url,
                object_name=handle.object_name,
                poll_interval_seconds=1.0,
                timeout_seconds=5.0,
            )
