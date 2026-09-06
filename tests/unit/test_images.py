"""Unit tests for tests/common/images.py — pure, no network, no GCP."""

from __future__ import annotations

import pytest

from tests.common.images import (
    CONTENT_TYPE_TO_FORMAT,
    GeneratedImage,
    make_test_image,
    read_image_dimensions,
)


class TestMakeTestImage:
    def test_defaults_produce_a_jpeg_larger_than_thumbnail_size(self) -> None:
        image = make_test_image()

        assert isinstance(image, GeneratedImage)
        assert image.content_type == "image/jpeg"
        assert image.filename.endswith(".jpg")
        assert image.width == 800
        assert image.height == 600
        assert len(image.data) > 0

    @pytest.mark.parametrize(
        ("content_type", "expected_extension"),
        [
            ("image/png", "png"),
            ("image/jpeg", "jpg"),
            ("image/gif", "gif"),
            ("image/webp", "webp"),
        ],
    )
    def test_supports_every_content_type_the_functions_accept(
        self, content_type: str, expected_extension: str
    ) -> None:
        image = make_test_image(content_type=content_type, width=64, height=64)

        assert image.content_type == content_type
        assert image.filename.endswith(f".{expected_extension}")
        assert read_image_dimensions(image.data) == (64, 64)

    def test_rejects_unsupported_content_type(self) -> None:
        with pytest.raises(ValueError, match="content_type must be one of"):
            make_test_image(content_type="image/bmp")

    def test_custom_filename_is_used_as_stem(self) -> None:
        image = make_test_image(filename="my-photo", content_type="image/png")
        assert image.filename == "my-photo.png"

    def test_generated_bytes_actually_decode_to_requested_size(self) -> None:
        image = make_test_image(width=333, height=111, content_type="image/png")
        assert read_image_dimensions(image.data) == (333, 111)

    def test_every_declared_content_type_is_covered_by_the_map(self) -> None:
        # Guards against silently adding a content type to the allowlist
        # without also giving make_test_image a way to produce it.
        for content_type in CONTENT_TYPE_TO_FORMAT:
            image = make_test_image(content_type=content_type, width=10, height=10)
            assert image.data


class TestReadImageDimensions:
    def test_matches_dimensions_used_at_creation(self) -> None:
        image = make_test_image(width=42, height=17, content_type="image/png")
        assert read_image_dimensions(image.data) == (42, 17)
