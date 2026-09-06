"""Unit tests for tests/common/pipeline_client.py — requests fully mocked."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.common.pipeline_client import (
    PipelineError,
    ThumbnailTimeoutError,
    UploadHandle,
    download_bytes,
    poll_for_download_url,
    put_image_bytes,
    request_upload_url,
)


def _mock_response(*, status_code: int = 200, json_body: Any = None, text: str = "") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = text
    response.content = json_body if isinstance(json_body, bytes) else b""
    return response


class TestRequestUploadUrl:
    def test_returns_handle_on_success(self) -> None:
        response = _mock_response(
            json_body={"uploadUrl": "https://signed/put", "objectName": "123-cat.jpg"}
        )
        with patch("tests.common.pipeline_client.requests.post", return_value=response) as post:
            handle = request_upload_url(
                "https://fn.example", filename="cat.jpg", content_type="image/jpeg"
            )

        assert handle == UploadHandle(object_name="123-cat.jpg", upload_url="https://signed/put")
        post.assert_called_once()
        _, kwargs = post.call_args
        assert kwargs["params"] == {"action": "upload"}
        assert kwargs["json"] == {"filename": "cat.jpg", "contentType": "image/jpeg"}

    def test_raises_on_non_200(self) -> None:
        response = _mock_response(status_code=400, text="bad content type")
        with patch("tests.common.pipeline_client.requests.post", return_value=response):
            with pytest.raises(PipelineError, match="400"):
                request_upload_url(
                    "https://fn.example", filename="x.jpg", content_type="image/jpeg"
                )

    def test_raises_on_malformed_response_body(self) -> None:
        response = _mock_response(json_body={"unexpected": "shape"})
        with patch("tests.common.pipeline_client.requests.post", return_value=response):
            with pytest.raises(PipelineError, match="unexpected upload response shape"):
                request_upload_url(
                    "https://fn.example", filename="x.jpg", content_type="image/jpeg"
                )


class TestPutImageBytes:
    @pytest.mark.parametrize("status_code", [200, 201])
    def test_accepts_200_and_201(self, status_code: int) -> None:
        response = _mock_response(status_code=status_code)
        with patch("tests.common.pipeline_client.requests.put", return_value=response) as put:
            put_image_bytes("https://signed/put", data=b"bytes", content_type="image/png")

        put.assert_called_once()
        _, kwargs = put.call_args
        assert kwargs["data"] == b"bytes"
        assert kwargs["headers"] == {"Content-Type": "image/png"}

    def test_raises_on_failure_status(self) -> None:
        response = _mock_response(status_code=403, text="signature expired")
        with patch("tests.common.pipeline_client.requests.put", return_value=response):
            with pytest.raises(PipelineError, match="403"):
                put_image_bytes("https://signed/put", data=b"bytes", content_type="image/png")


class TestPollForDownloadUrl:
    def test_returns_immediately_when_thumbnail_already_exists(self) -> None:
        response = _mock_response(json_body={"exists": True, "downloadUrl": "https://signed/get"})
        with patch("tests.common.pipeline_client.requests.get", return_value=response):
            url = poll_for_download_url(
                "https://fn.example",
                object_name="123-cat.jpg",
                poll_interval_seconds=0.01,
                timeout_seconds=1.0,
            )
        assert url == "https://signed/get"

    def test_polls_until_it_exists(self) -> None:
        not_yet = _mock_response(json_body={"exists": False})
        ready = _mock_response(json_body={"exists": True, "downloadUrl": "https://signed/get"})

        with (
            patch(
                "tests.common.pipeline_client.requests.get",
                side_effect=[not_yet, not_yet, ready],
            ) as get,
            patch("tests.common.pipeline_client.time.sleep") as sleep,
        ):
            url = poll_for_download_url(
                "https://fn.example",
                object_name="123-cat.jpg",
                poll_interval_seconds=0.01,
                timeout_seconds=5.0,
            )

        assert url == "https://signed/get"
        assert get.call_count == 3
        assert sleep.call_count == 2

    def test_times_out_if_never_exists(self) -> None:
        not_yet = _mock_response(json_body={"exists": False})

        with (
            patch("tests.common.pipeline_client.requests.get", return_value=not_yet),
            patch("tests.common.pipeline_client.time.sleep"),
        ):
            with pytest.raises(ThumbnailTimeoutError, match="did not appear"):
                poll_for_download_url(
                    "https://fn.example",
                    object_name="never.jpg",
                    poll_interval_seconds=0.01,
                    timeout_seconds=0.0,
                )

    def test_raises_if_exists_true_but_no_download_url(self) -> None:
        malformed = _mock_response(json_body={"exists": True})
        with patch("tests.common.pipeline_client.requests.get", return_value=malformed):
            with pytest.raises(PipelineError, match="no downloadUrl"):
                poll_for_download_url(
                    "https://fn.example",
                    object_name="x.jpg",
                    poll_interval_seconds=0.01,
                    timeout_seconds=1.0,
                )

    def test_raises_on_non_200(self) -> None:
        response = _mock_response(status_code=500, text="internal error")
        with patch("tests.common.pipeline_client.requests.get", return_value=response):
            with pytest.raises(PipelineError, match="500"):
                poll_for_download_url(
                    "https://fn.example",
                    object_name="x.jpg",
                    poll_interval_seconds=0.01,
                    timeout_seconds=1.0,
                )


class TestDownloadBytes:
    def test_returns_content_on_success(self) -> None:
        response = _mock_response(status_code=200, json_body=b"thumbnail-bytes")
        with patch("tests.common.pipeline_client.requests.get", return_value=response):
            data = download_bytes("https://signed/get")
        assert data == b"thumbnail-bytes"

    def test_raises_on_failure(self) -> None:
        response = _mock_response(status_code=404, text="not found")
        with patch("tests.common.pipeline_client.requests.get", return_value=response):
            with pytest.raises(PipelineError, match="404"):
                download_bytes("https://signed/get")
