from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal, override

from PIL import Image

from odoo.exceptions import UserError as _UserError
from odoo.libs.colors import hex_to_rgb
from odoo.libs.image import (
    IMAGE_MAX_RESOLUTION,
    ImageDecodeError,
    ImageTooLargeError,
    NotWebpError,
    average_dominant_color,
    image_apply_opt,
    image_data_uri,
    image_fix_orientation,
    image_guess_size_from_field_name,
    image_to_base64,
)
from odoo.libs.image import (
    ImageEncodeError as _ImageEncodeError,
)
from odoo.libs.image import (
    ImageProcess as _ImageProcessBase,
)
from odoo.libs.image import (
    base64_to_image as _base64_to_image_base,
)
from odoo.libs.image import (
    binary_to_image as _binary_to_image_base,
)
from odoo.libs.image import (
    get_webp_size as _get_webp_size_base,
)
from odoo.libs.image import (
    image_process as _image_process_base,
)
from odoo.libs.image import (
    is_image_size_above as _is_image_size_above_base,
)
from odoo.tools.translate import LazyTranslate as _LazyTranslate

__all__ = [
    "IMAGE_MAX_RESOLUTION",
    "ImageDecodeError",
    "ImageProcess",
    "ImageTooLargeError",
    "NotWebpError",
    "average_dominant_color",
    "base64_to_image",
    "binary_to_image",
    "get_webp_size",
    "hex_to_rgb",
    "image_apply_opt",
    "image_data_uri",
    "image_fix_orientation",
    "image_guess_size_from_field_name",
    "image_process",
    "image_to_base64",
    "is_image_size_above",
]
_lt = _LazyTranslate("base")


@contextmanager
def _decoded_as_user_error() -> Iterator[None]:
    try:
        yield
    except ImageDecodeError as e:
        raise _UserError(_lt("This file could not be decoded as an image file.")) from e
    except _ImageEncodeError as e:
        raise _UserError(_lt("This image could not be encoded.")) from e
    except ImageTooLargeError as e:
        raise _UserError(
            _lt(
                "Too large image (above %sMpx), reduce the image size.",
                str(IMAGE_MAX_RESOLUTION / 1e6),
            )
        ) from e


class ImageProcess(_ImageProcessBase):
    def __init__(self, source: bytes | None, verify_resolution: bool = True) -> None:
        try:
            with _decoded_as_user_error():
                super().__init__(source, verify_resolution)
        except ValueError as e:
            raise _UserError(str(e)) from e

    @override
    def _decode_upright(self) -> None:
        with _decoded_as_user_error():
            super()._decode_upright()

    @override
    def image_quality(
        self, quality: int = 0, output_format: str = ""
    ) -> bytes | Literal[False]:
        with _decoded_as_user_error():
            return super().image_quality(quality, output_format)


def image_process(
    source: bytes | Literal[False] | None,
    size: tuple[int, int] = (0, 0),
    verify_resolution: bool = False,
    quality: int = 0,
    expand: bool = False,
    crop: str | None = None,
    colorize: bool | tuple[int, int, int] = False,
    output_format: str = "",
    padding: int | bool = False,
) -> bytes | Literal[False] | None:
    return _image_process_base(
        source,
        size=size,
        verify_resolution=verify_resolution,
        quality=quality,
        expand=expand,
        crop=crop,
        colorize=colorize,
        output_format=output_format,
        padding=padding,
        processor=ImageProcess,
    )


def binary_to_image(source: bytes) -> Image.Image:
    with _decoded_as_user_error():
        return _binary_to_image_base(source)


def base64_to_image(base64_source: str | bytes) -> Image.Image:
    with _decoded_as_user_error():
        return _base64_to_image_base(base64_source)


def get_webp_size(source: bytes) -> tuple[int, int]:
    try:
        with _decoded_as_user_error():
            return _get_webp_size_base(source)
    except NotWebpError as e:
        raise _UserError(_lt("This file is not a webp file.")) from e


def is_image_size_above(
    base64_source_1: str | bytes, base64_source_2: str | bytes
) -> bool:
    try:
        return _is_image_size_above_base(base64_source_1, base64_source_2)
    except ValueError as e:
        raise _UserError(_lt("This file could not be decoded as an image file.")) from e
