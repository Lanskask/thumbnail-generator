"""
End-to-end test against a *live* Cloudflare deployment (cloudflare/terraform).

Set CLOUDFLARE_URL to the Worker's base URL, e.g.
  CLOUDFLARE_URL=https://thumbnail-generator.<subdomain>.workers.dev make test-e2e-cloudflare
or to a local `wrangler dev` URL. Without it every test is skipped.

Path exercised (same as the frontend):
  POST /api?action=upload -> PUT /api/put/<name> (Worker resizes via the Images binding, stores
  in R2) -> GET /api?action=download -> GET /api/thumb/<name> -> assert size <= 200x200.
"""

from __future__ import annotations

import pytest
import requests

from tests.common.cloudflare_client import (
    CloudflarePipelineError,
    fetch_thumbnail,
    load_base_url,
    put_image,
    request_upload,
)
from tests.common.images import make_test_image, read_image_dimensions

pytestmark = pytest.mark.e2e_cloudflare

THUMBNAIL_MAX_DIMENSION: int = 200
OBJECT_NAME = "1699999999-abcdef12-cat.jpg"


@pytest.fixture(scope="session")
def base_url() -> str:
    url = load_base_url()
    if url is None:
        pytest.skip("CLOUDFLARE_URL is not set (deployed Worker URL or local `wrangler dev` URL)")
    return url


def test_frontend_is_served_with_same_origin_api(base_url: str) -> None:
    response = requests.get(f"{base_url}/", timeout=30)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'const UPLOAD_FUNCTION_URL = "/api"' in response.text


@pytest.mark.parametrize("content_type", ["image/jpeg", "image/png", "image/webp", "image/gif"])
def test_upload_produces_thumbnail_within_200x200(base_url: str, content_type: str) -> None:
    image = make_test_image(width=800, height=600, content_type=content_type)

    upload = request_upload(base_url, filename=image.filename, content_type=image.content_type)
    put = put_image(upload.upload_url, data=image.data, content_type=image.content_type)
    assert put.status_code == 200, put.text

    thumbnail = fetch_thumbnail(base_url, object_name=upload.object_name)
    width, height = read_image_dimensions(thumbnail)
    assert width <= THUMBNAIL_MAX_DIMENSION
    assert height <= THUMBNAIL_MAX_DIMENSION
    assert (width, height) == (200, 150), "aspect ratio 4:3 must be preserved"


def test_small_image_is_not_upscaled(base_url: str) -> None:
    image = make_test_image(width=50, height=40, content_type="image/png")
    upload = request_upload(base_url, filename=image.filename, content_type=image.content_type)
    assert put_image(upload.upload_url, data=image.data, content_type=image.content_type).ok

    thumbnail = fetch_thumbnail(base_url, object_name=upload.object_name)
    assert read_image_dimensions(thumbnail) == (50, 40)


def test_thumbnail_does_not_exist_before_upload(base_url: str) -> None:
    response = requests.get(
        f"{base_url}/api",
        params={"action": "download", "objectName": OBJECT_NAME},
        timeout=30,
    )
    assert response.status_code == 200
    assert response.json() == {"exists": False}


def test_upload_request_validation(base_url: str) -> None:
    no_name = requests.post(
        f"{base_url}/api",
        params={"action": "upload"},
        json={"contentType": "image/png"},
        timeout=30,
    )
    bad_type = requests.post(
        f"{base_url}/api",
        params={"action": "upload"},
        json={"filename": "a.txt", "contentType": "text/plain"},
        timeout=30,
    )
    unknown = requests.get(f"{base_url}/api", params={"action": "nope"}, timeout=30)
    assert [no_name.status_code, bad_type.status_code, unknown.status_code] == [400, 400, 400]


def test_put_rejects_bad_name_type_and_size(base_url: str) -> None:
    ok_headers = {"Content-Type": "image/jpeg"}
    bad_name = requests.put(
        f"{base_url}/api/put/evil.jpg", data=b"x", headers=ok_headers, timeout=30
    )
    bad_type = requests.put(
        f"{base_url}/api/put/{OBJECT_NAME}",
        data=b"x",
        headers={"Content-Type": "text/plain"},
        timeout=30,
    )
    too_big = requests.put(
        f"{base_url}/api/put/{OBJECT_NAME}",
        data=b"\0" * (10 * 1024 * 1024 + 1),
        headers=ok_headers,
        timeout=60,
    )
    assert [bad_name.status_code, bad_type.status_code, too_big.status_code] == [400, 415, 413]


def test_thumb_route_only_serves_thumbnails(base_url: str) -> None:
    response = requests.get(f"{base_url}/api/thumb/secret", timeout=30)
    assert response.status_code == 404


def test_fetch_thumbnail_times_out_for_unknown_object(base_url: str) -> None:
    with pytest.raises(CloudflarePipelineError):
        fetch_thumbnail(
            base_url,
            object_name="1699999999-00000000-missing.jpg",
            timeout_seconds=1.0,
            poll_interval_seconds=0.2,
        )
