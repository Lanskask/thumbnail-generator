"""
Test-image generation.

No binary fixtures are checked into the repo — every test image is generated
in-memory with Pillow so the test suite has zero binary assets to maintain
and can produce images of any size/format/color on demand.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

# (content_type, Pillow format, file extension) for each format the deployed
# functions accept — kept in sync with _ALLOWED_CONTENT_TYPES in
# functions/get_upload_url/main.py and SUPPORTED_EXTENSIONS in
# functions/make_thumbnail/main.py.
CONTENT_TYPE_TO_FORMAT: dict[str, tuple[str, str]] = {
    "image/png": ("PNG", "png"),
    "image/jpeg": ("JPEG", "jpg"),
    "image/gif": ("GIF", "gif"),
    "image/webp": ("WEBP", "webp"),
}


@dataclass(frozen=True)
class GeneratedImage:
    """An in-memory test image ready to upload."""

    filename: str
    content_type: str
    data: bytes
    width: int
    height: int


def make_test_image(
    *,
    width: int = 800,
    height: int = 600,
    content_type: str = "image/jpeg",
    color: tuple[int, int, int] = (255, 0, 0),
    filename: str = "test-upload",
) -> GeneratedImage:
    """Generate a solid-color image of the given size/format in memory.

    Defaults to a size clearly larger than the 200x200 thumbnail target, so
    a passing resize assertion actually proves the pipeline resized the
    image rather than merely round-tripping a same-size file.
    """
    if content_type not in CONTENT_TYPE_TO_FORMAT:
        allowed = sorted(CONTENT_TYPE_TO_FORMAT)
        raise ValueError(f"content_type must be one of {allowed}, got {content_type!r}")

    pillow_format, extension = CONTENT_TYPE_TO_FORMAT[content_type]

    mode = "RGB" if pillow_format in ("JPEG", "PNG") else "RGB"
    image = Image.new(mode, (width, height), color=color)

    buffer = io.BytesIO()
    image.save(buffer, format=pillow_format)
    data = buffer.getvalue()

    return GeneratedImage(
        filename=f"{filename}.{extension}",
        content_type=content_type,
        data=data,
        width=width,
        height=height,
    )


def read_image_dimensions(data: bytes) -> tuple[int, int]:
    """Return (width, height) of an in-memory image, without saving to disk."""
    with Image.open(io.BytesIO(data)) as img:
        return img.size
