import base64
import binascii
import contextlib
import io
import re
import struct
from collections.abc import Callable, Iterator
from random import randrange
from typing import Any, Literal, Self, override

from PIL import (
    IcoImagePlugin,
    Image,
    ImageOps,
    ImageSequence,
)
from PIL.Image import Image as PILImage
from PIL.Image import Palette, Resampling

from odoo.libs.debug_log import DebugLog
from odoo.libs.filesystem.mimetypes import is_svg, opens_on_markup

__all__ = [
    "IMAGE_MAX_RESOLUTION",
    "ImageDecodeError",
    "ImageEncodeError",
    "ImageError",
    "ImageProcess",
    "ImageTooLargeError",
    "NotWebpError",
    "average_dominant_color",
    "base64_image_subtype",
    "base64_to_image",
    "binary_to_image",
    "get_webp_size",
    "image_apply_opt",
    "image_data_uri",
    "image_fix_orientation",
    "image_guess_size_from_field_name",
    "image_process",
    "image_to_base64",
    "is_image_size_above",
    "is_svg",
]


class ImageError(ValueError):
    pass


class ImageDecodeError(ImageError):
    pass


class ImageEncodeError(ImageError):
    pass


class ImageTooLargeError(ImageError):
    pass


class NotWebpError(ImageError):
    pass


_EXIF_TAG_ORIENTATION = 0x112

IMAGE_MAX_RESOLUTION = 50e6

_ANIMATED_FORMATS = frozenset({"GIF", "WEBP", "PNG"})
_debug = DebugLog(__name__)


Image.preinit()

_TRANSPOSED_ORIENTATIONS = frozenset({5, 6, 7, 8})


def image_fix_orientation(image: PILImage) -> PILImage:
    return ImageOps.exif_transpose(image)


_CORRUPT_IMAGE_ERRORS = (
    OSError,
    SyntaxError,
    TypeError,
    KeyError,
    IndexError,
    EOFError,
    ValueError,
    struct.error,
    ZeroDivisionError,
)


@contextlib.contextmanager
def _decoding(stage: str, source: bytes | Literal[False] | None) -> Iterator[None]:
    try:
        yield
    except ImageError:
        raise
    except _CORRUPT_IMAGE_ERRORS as error:
        _debug.logic(
            "image.decode_failed",
            stage=stage,
            error=type(error).__name__,
            source_bytes=len(source or b""),
        )
        msg = "This file could not be decoded as an image file."
        raise ImageDecodeError(msg) from error


class _SourceStream(io.BytesIO):
    starved = False

    @override
    def read(self, size: int | None = -1, /) -> bytes:
        data = super().read(size)
        if not data and size != 0:
            self.starved = True
        return data


def _watch_source(image: PILImage) -> _SourceStream | None:
    stream = getattr(image, "fp", None)
    if not isinstance(stream, _SourceStream):
        return None
    stream.starved = False
    attributes = vars(image)
    load_read = getattr(image, "load_read", None)
    if load_read is not None and "load_read" not in attributes:

        def watched_load_read(size: int) -> bytes:
            data: bytes = load_read(size)
            if not data:
                stream.starved = True
            return data

        attributes["load_read"] = watched_load_read
    return stream


def _check_image_complete(image: PILImage, stream: _SourceStream | None) -> None:
    if stream is None:
        return
    truncated = stream.starved
    if not truncated and isinstance(image, IcoImagePlugin.IcoImageFile):
        with stream.getbuffer() as view:
            available = view.nbytes
        truncated = any(
            entry.offset + entry.size > available for entry in image.ico.entry
        )
    if truncated:
        _debug.logic("image.truncated", format=image.format, mode=image.mode)
        msg = "This file could not be decoded as an image file."
        raise ImageDecodeError(msg)


def _load_whole(image: PILImage) -> None:
    stream = _watch_source(image)
    image.load()
    _check_image_complete(image, stream)


def _checked_frames(image: PILImage) -> Iterator[PILImage]:
    stream = _watch_source(image)
    for frame in ImageSequence.Iterator(image):
        if stream is not None:
            stream.starved = False
        yield frame
        _check_image_complete(frame, stream)


@contextlib.contextmanager
def _encoding(image: PILImage, output_format: str) -> Iterator[None]:
    try:
        yield
    except ImageError:
        raise
    except _CORRUPT_IMAGE_ERRORS as error:
        _debug.logic(
            "image.encode_failed",
            format=output_format,
            mode=image.mode,
            width=image.width,
            height=image.height,
            error=type(error).__name__,
        )
        msg = f"This image could not be encoded as {output_format}."
        raise ImageEncodeError(msg) from error


def image_apply_opt(image: PILImage, output_format: str, **params: Any) -> bytes:
    writers = Image.SAVE_ALL if params.get("save_all") else Image.SAVE
    format_name = output_format.upper()
    if format_name not in writers:
        Image.init()
    if format_name not in writers:
        msg = f"Pillow cannot write {output_format!r} images"
        raise ValueError(msg)
    with _decoding("pixels", None):
        _load_whole(image)
        if format_name == "JPEG" and image.mode not in ["1", "L", "RGB"]:
            image = image.convert("RGB")
    stream = io.BytesIO()
    with (
        _decoding("frames", None)
        if params.get("save_all")
        else _encoding(image, output_format)
    ):
        image.save(stream, format=output_format, **params)
    return stream.getvalue()


def image_to_base64(image: PILImage, output_format: str, **params: Any) -> bytes:
    stream = image_apply_opt(image, output_format, **params)
    return base64.b64encode(stream)


_DATA_URI_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"\x00\x00\x01\x00", "x-icon"),
)
_NOT_BASE64 = re.compile(rb"[^A-Za-z0-9+/]")
_SIGNATURE_HEAD_BASE64 = 64
_SUBTYPE_HEAD_BASE64 = 2048 * 4 // 3


def _base64_head(base64_source: bytes, chars: int) -> bytes:
    head = _NOT_BASE64.sub(b"", base64_source[:chars])
    return base64.b64decode(head[: len(head) - len(head) % 4])


def base64_image_subtype(base64_source: bytes) -> str:
    data = _base64_head(base64_source, _SIGNATURE_HEAD_BASE64)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    for signature, subtype in _DATA_URI_SIGNATURES:
        if data.startswith(signature):
            return subtype
    if not opens_on_markup(data):
        return "png"
    if is_svg(_base64_head(base64_source, _SUBTYPE_HEAD_BASE64)):
        return "svg+xml"
    if len(base64_source) > _SUBTYPE_HEAD_BASE64 and is_svg(
        _base64_head(base64_source, len(base64_source))
    ):
        return "svg+xml"
    return "png"


def image_data_uri(base64_source: bytes) -> str:
    subtype = base64_image_subtype(base64_source)
    return f"data:image/{subtype};base64,{base64_source.decode()}"


_UNREDUCIBLE_MODES = frozenset({"I", "I;16", "I;16L", "I;16B", "I;16N"})
_PADDED_AS_RGBA = frozenset({"1", "P", "PA", "LA"})


def _to_web_palette(frame: PILImage) -> PILImage:
    return frame.convert("RGBA").convert("P", palette=Palette.WEB, colors=256)


def _to_rgba(frame: PILImage) -> PILImage:
    return frame.convert("RGBA")


def _to_shared_palette(frames: list[PILImage]) -> list[PILImage]:
    sheet = Image.new(
        "RGBA", (max(f.width for f in frames), sum(f.height for f in frames))
    )
    top = 0
    for frame in frames:
        sheet.paste(frame, (0, top))
        top += frame.height
    sheet = _to_web_palette(sheet)
    shared = []
    top = 0
    for frame in frames:
        piece = sheet.crop((0, top, frame.width, top + frame.height))
        piece.info = dict(frame.info)
        shared.append(piece)
        top += frame.height
    return shared


_HEADER_ORIENTATION_FORMATS = frozenset({"JPEG", "MPO", "WEBP", "PNG"})


def _exif_orientation(image: PILImage) -> int:
    try:
        orientation: int = image.getexif().get(_EXIF_TAG_ORIENTATION, 1)
        return orientation
    except SyntaxError, ValueError, TypeError, struct.error, OSError:
        return 1


def _header_orientation(image: PILImage, source: bytes) -> int | None:
    image_format = (image.format or "").upper()
    if image_format not in _HEADER_ORIENTATION_FORMATS:
        return None
    if image_format == "PNG" and "exif" not in image.info:
        return None if b"eXIf" in source else 1
    return _exif_orientation(image)


class ImageProcess:
    source: bytes | Literal[False]
    original_format: str
    _frame_transform: Callable[[PILImage], PILImage] | None = None

    def __init__(
        self, source: bytes | Literal[False] | None, verify_resolution: bool = True
    ) -> None:
        self.source = source or False
        self.operations_count = 0
        self.original_format = ""
        self.animated = False
        self.animated_frames: list[PILImage] = []
        self._image: PILImage | Literal[False] = False
        self._decoded = True
        self._size: tuple[int, int] | None = None

        if not source or is_svg(source):
            _debug.logic(
                "image.skipped",
                reason="empty" if not source else "svg",
                source_bytes=len(source) if source else 0,
            )
        else:
            image = binary_to_image(source)

            w, h = image.size
            image_format = (getattr(image, "format", None) or "").upper()
            if image_format == "MPO":
                image_format = "JPEG"
            with _decoding("header", source):
                frames = getattr(image, "n_frames", 1)
            animated = frames > 1 and image_format in _ANIMATED_FORMATS
            decoded_frames = frames if animated else 1
            if verify_resolution and w * h * decoded_frames > IMAGE_MAX_RESOLUTION:
                _debug.logic(
                    "image.too_large",
                    width=w,
                    height=h,
                    frames=decoded_frames,
                    pixels=w * h * decoded_frames,
                    limit=IMAGE_MAX_RESOLUTION,
                    format=image_format,
                )
                raise ImageTooLargeError(
                    f"Too large image (above {IMAGE_MAX_RESOLUTION / 1e6}Mpx), reduce the image size."
                )

            self.original_format = image_format
            self.animated = animated
            self._image = image
            self._decoded = self.animated
            with _decoding("header", source):
                orientation = 1 if self.animated else _header_orientation(image, source)
            _debug.lifecycle(
                "image.opened",
                format=self.original_format,
                mode=image.mode,
                width=w,
                height=h,
                animated=self.animated,
                orientation=orientation,
                verified=verify_resolution,
            )
            if orientation is None:
                self._decode_upright()
            elif orientation in _TRANSPOSED_ORIENTATIONS:
                self._size = (h, w)
            else:
                self._size = (w, h)

    @property
    def image(self) -> PILImage | Literal[False]:
        if not self._decoded:
            self._decode_upright()
        return self._image

    @image.setter
    def image(self, image: PILImage | Literal[False]) -> None:
        self._image = image
        self._decoded = True

    @property
    def size(self) -> tuple[int, int] | None:
        if not self._image:
            return None
        if self._decoded:
            size: tuple[int, int] = self._image.size
            return size
        return self._size

    @property
    def _pixels(self) -> PILImage:
        image = self.image
        assert image is not False, "an operation reached an image-less process"
        return image

    @property
    def _dimensions(self) -> tuple[int, int]:
        size = self.size
        assert size is not None, "an operation reached an image-less process"
        return size

    def decode_pixels(self) -> Self:
        if not self._decoded or (self.animated and not self.animated_frames):
            self._decode_upright()
        return self

    def _decode_upright(self) -> None:
        image = self._image
        assert image is not False
        _debug.logic(
            "image.decoded",
            format=self.original_format,
            animated=self.animated,
            source_bytes=len(self.source or b""),
        )
        if self.animated:
            transform = self._frame_transform
            with _decoding("frames", self.source):
                if transform is None:
                    for frame in _checked_frames(image):
                        frame.load()
                    image.seek(0)
                    return
                frames = [transform(frame) for frame in _checked_frames(image)]
            self._set_frames(frames)
            return
        with _decoding("pixels", self.source):
            _load_whole(image)
            if _exif_orientation(image) != 1:
                image = image_fix_orientation(image)
            self.image = image

    @property
    def _frames(self) -> list[PILImage]:
        return [self._pixels, *self.animated_frames]

    @property
    def _frame_wise(self) -> bool:
        return self.animated or self.original_format == "GIF"

    def _transform_frames(self, transform: Callable[[PILImage], PILImage]) -> None:
        if self.animated and not self.animated_frames:
            self._frame_transform = transform
            try:
                self._decode_upright()
            finally:
                self._frame_transform = None
            return
        self._set_frames([transform(frame) for frame in self._frames])

    def _set_frames(self, frames: list[PILImage]) -> None:
        self.image = frames[0]
        self.animated_frames = frames[1:]

    def image_quality(
        self, quality: int = 0, output_format: str = ""
    ) -> bytes | Literal[False]:
        if not self._image:
            return self.source

        source = self.source
        assert source is not False, "an image was decoded from a falsy source"

        output_format = output_format.upper() or self.original_format
        if output_format == "BMP":
            output_format = "PNG"
        elif output_format not in ["PNG", "JPEG", "GIF", "ICO", "WEBP"]:
            output_format = "JPEG"

        if (
            not self.operations_count
            and output_format == self.original_format
            and not quality
        ):
            _debug.logic(
                "image.quality.passthrough",
                format=output_format,
                reason="untouched",
                source_bytes=len(source),
            )
            return self.source

        output_image = self._pixels
        opt: dict[str, Any] = {"output_format": output_format}

        if output_format == "PNG":
            opt["optimize"] = True
            if self.animated:
                if quality or len({frame.mode for frame in self._frames}) > 1:
                    self._transform_frames(_to_rgba)
                if quality:
                    self._set_frames(_to_shared_palette(self._frames))
                output_image = self._pixels
            elif quality and output_image.mode != "P":
                output_image = _to_web_palette(output_image)
        if output_format == "JPEG":
            opt["optimize"] = True
            opt["quality"] = quality or 95
        if output_format == "GIF":
            opt["optimize"] = True
            opt["save_all"] = True
            opt["append_images"] = self.animated_frames
        if output_format == "WEBP":
            opt["quality"] = quality or 80
        if output_format in ("PNG", "WEBP") and self.animated:
            opt["save_all"] = True
            opt["append_images"] = self.animated_frames

        if output_image.mode not in ["1", "L", "P", "RGB", "RGBA"] or (
            output_format == "JPEG" and output_image.mode == "RGBA"
        ):
            output_image = output_image.convert("RGB")

        output_bytes = image_apply_opt(output_image, **opt)
        if (
            len(output_bytes) >= len(source)
            and self.original_format == output_format
            and not self.operations_count
        ):
            _debug.logic(
                "image.quality.passthrough",
                format=output_format,
                reason="not_smaller",
                source_bytes=len(source),
                output_bytes=len(output_bytes),
            )
            return source
        _debug.logic(
            "image.quality.encoded",
            format=output_format,
            original=self.original_format,
            mode=output_image.mode,
            quality=quality,
            operations=self.operations_count,
            source_bytes=len(source),
            output_bytes=len(output_bytes),
        )
        return output_bytes

    def resize(
        self,
        max_width: float | None = 0,
        max_height: float | None = 0,
        expand: bool = False,
    ) -> Self:
        max_width, max_height = int(max_width or 0), int(max_height or 0)
        if self._image and (max_width or max_height):
            w, h = self._dimensions
            asked_width = max_width or max(1, (w * max_height) // h)
            asked_height = max_height or max(1, (h * max_width) // w)
            if self._frame_wise:
                if expand and (asked_width > w or asked_height > h):

                    def grow(frame: PILImage) -> PILImage:
                        return frame.resize((asked_width, asked_height))

                    self._transform_frames(grow)
                    self.operations_count += 1
                elif asked_width < w or asked_height < h:

                    def shrink(frame: PILImage) -> PILImage:
                        frame = frame.copy()
                        frame.thumbnail((asked_width, asked_height), Resampling.LANCZOS)
                        return frame

                    self._transform_frames(shrink)
                    self.operations_count += 1
                return self
            if expand and (asked_width > w or asked_height > h):
                self.image = self._pixels.resize((asked_width, asked_height))
                self.operations_count += 1
                return self
            if asked_width < w or asked_height < h:
                self._pixels.thumbnail(
                    (asked_width, asked_height),
                    Resampling.LANCZOS,
                    reducing_gap=None
                    if self._pixels.mode in _UNREDUCIBLE_MODES
                    else 2.0,
                )
                if self._pixels.width != w or self._pixels.height != h:
                    self.operations_count += 1
        return self

    def crop_resize(
        self,
        max_width: float | None,
        max_height: float | None,
        center_x: float = 0.5,
        center_y: float = 0.5,
    ) -> Self:
        max_width, max_height = int(max_width or 0), int(max_height or 0)
        if not (self._image and max_width and max_height):
            return self.resize(max_width, max_height)
        w, h = self._dimensions
        if w * max_height > h * max_width:
            new_w, new_h = max(1, round(h * max_width / max_height)), h
        else:
            new_w, new_h = w, max(1, round(w * max_height / max_width))
        x_offset = int((w - new_w) * center_x)
        y_offset = int((h - new_h) * center_y)
        crop_box = (x_offset, y_offset, x_offset + new_w, y_offset + new_h)

        if new_w > max_width or new_h > max_height:

            def transform(frame: PILImage) -> PILImage:
                return frame.crop(crop_box).resize(
                    (max_width, max_height),
                    Resampling.LANCZOS,
                    reducing_gap=None if frame.mode in _UNREDUCIBLE_MODES else 2.0,
                )

        elif (new_w, new_h) != (w, h):

            def transform(frame: PILImage) -> PILImage:
                return frame.crop(crop_box)

        else:
            return self
        self._apply(transform)
        return self

    def colorize(self, color: tuple[int, int, int] | None = None) -> Self:
        if color is None:
            color = (
                randrange(32, 224, 24),
                randrange(32, 224, 24),
                randrange(32, 224, 24),
            )
        if self._image:

            def _get_frame_colorized(frame: PILImage) -> PILImage:
                if frame.mode == "P":
                    frame = frame.convert("RGBA")
                filled = Image.new("RGB", frame.size, color)
                mask = frame if frame.mode in ("1", "L", "LA", "RGBA") else None
                filled.paste(frame, mask=mask)
                return filled

            self._apply(_get_frame_colorized)
        return self

    def add_padding(self, padding: int) -> Self:
        if self._image:
            img_width, img_height = self._dimensions
            if 2 * padding >= min(img_width, img_height):
                raise ValueError(
                    f"padding {padding} is too large for a "
                    f"{img_width}x{img_height} image"
                )
            inner = (img_width - 2 * padding, img_height - 2 * padding)

            as_rgba = self._frame_wise

            def pad(frame: PILImage) -> PILImage:
                if as_rgba or frame.mode in _PADDED_AS_RGBA:
                    frame = frame.convert("RGBA")
                return ImageOps.expand(frame.resize(inner), border=padding)

            self._apply(pad)
        return self

    def _apply(self, transform: Callable[[PILImage], PILImage]) -> None:
        if self._frame_wise:
            self._transform_frames(transform)
        else:
            self.image = transform(self._pixels)
        self.operations_count += 1


def image_process(
    source: bytes | Literal[False] | None,
    size: tuple[float | None, float | None] = (0, 0),
    verify_resolution: bool = False,
    quality: int = 0,
    expand: bool = False,
    crop: str | None = None,
    colorize: bool | tuple[int, int, int] = False,
    output_format: str = "",
    padding: int | bool = False,
    processor: type[ImageProcess] = ImageProcess,
) -> bytes | Literal[False] | None:
    if not source or (
        (not size or (not size[0] and not size[1]))
        and not verify_resolution
        and not quality
        and not crop
        and not colorize
        and not output_format
        and not padding
    ):
        return source

    with _debug.perf(
        "image.process",
        source_bytes=len(source),
        size=f"{size[0]}x{size[1]}" if size else None,
        crop=crop,
        quality=quality,
        output_format=output_format or None,
    ):
        image = processor(source, verify_resolution)
        if verify_resolution:
            image.decode_pixels()
        if size:
            if crop:
                center_x = 0.5
                center_y = 0.5
                if crop == "top":
                    center_y = 0
                elif crop == "bottom":
                    center_y = 1
                image.crop_resize(
                    max_width=size[0],
                    max_height=size[1],
                    center_x=center_x,
                    center_y=center_y,
                )
            else:
                image.resize(max_width=size[0], max_height=size[1], expand=expand)
        if padding:
            image.add_padding(padding)
        if colorize:
            image.colorize(colorize if isinstance(colorize, tuple) else None)
        return image.image_quality(quality=quality, output_format=output_format)


def average_dominant_color(
    colors: list[tuple[int, tuple[int, int, int, int]]],
    mitigate: int = 175,
    max_margin: int = 140,
) -> tuple[tuple[int, int, int], list[tuple[int, tuple[int, int, int, int]]]]:
    if not colors:
        msg = "colors must be a non-empty list of (count, (r, g, b, a)) tuples"
        raise ValueError(msg)
    total_count = sum(col[0] for col in colors)
    if not total_count:
        msg = "colors must contain at least one entry with a non-zero count"
        raise ValueError(msg)

    dominant_color = max(colors)
    dominant_rgb = dominant_color[1][:3]
    dominant_set = [dominant_color]
    remaining = []

    margins = [max_margin * (1 - dominant_color[0] / total_count)] * 3

    colors = [c for c in colors if c is not dominant_color]

    for color in colors:
        rgb = color[1]
        if (
            rgb[0] < dominant_rgb[0] + margins[0]
            and rgb[0] > dominant_rgb[0] - margins[0]
            and rgb[1] < dominant_rgb[1] + margins[1]
            and rgb[1] > dominant_rgb[1] - margins[1]
            and rgb[2] < dominant_rgb[2] + margins[2]
            and rgb[2] > dominant_rgb[2] - margins[2]
        ):
            dominant_set.append(color)
        else:
            remaining.append(color)

    dominant_avg = []
    for band in range(3):
        avg = total = 0
        for color in dominant_set:
            avg += color[0] * color[1][band]
            total += color[0]
        dominant_avg.append(int(avg / total))

    final_dominant = []
    brightest = max(dominant_avg)
    for band in range(3):
        value = (
            dominant_avg[band] / (brightest / mitigate)
            if brightest > mitigate
            else dominant_avg[band]
        )
        final_dominant.append(int(value))

    red, green, blue = final_dominant
    return (red, green, blue), remaining


def binary_to_image(source: bytes) -> PILImage:
    try:
        return Image.open(_SourceStream(source))
    except Image.DecompressionBombError:
        _debug.logic("image.decompression_bomb", source_bytes=len(source))
        msg = (
            f"Too large image (above {IMAGE_MAX_RESOLUTION / 1e6}Mpx), "
            "reduce the image size."
        )
        raise ImageTooLargeError(msg) from None
    except (*_CORRUPT_IMAGE_ERRORS, binascii.Error):
        _debug.logic(
            "image.decode_failed", source_bytes=len(source), head=source[:4].hex()
        )
        msg = "This file could not be decoded as an image file."
        raise ImageDecodeError(msg) from None


def base64_to_image(base64_source: str | bytes) -> PILImage:
    try:
        return binary_to_image(base64.b64decode(base64_source))
    except binascii.Error:
        msg = "This file could not be decoded as an image file."
        raise ImageDecodeError(msg) from None


def get_webp_size(source: bytes) -> tuple[int, int]:
    if len(source) < 16 or not (source[0:4] == b"RIFF" and source[8:15] == b"WEBPVP8"):
        msg = "This file is not a webp file."
        raise NotWebpError(msg)

    vp8_type = source[15]
    if vp8_type == 0x20 and len(source) >= 30:
        width_low, width_high, height_low, height_high = source[26:30]
        width = ((width_high << 8) + width_low) & 0x3FFF
        height = ((height_high << 8) + height_low) & 0x3FFF
        return (width, height)
    elif vp8_type == 0x58 and len(source) >= 30:
        (
            width_low,
            width_medium,
            width_high,
            height_low,
            height_medium,
            height_high,
        ) = source[24:30]
        width = 1 + (width_high << 16) + (width_medium << 8) + width_low
        height = 1 + (height_high << 16) + (height_medium << 8) + height_low
        return (width, height)
    elif vp8_type == 0x4C and len(source) >= 25 and source[20] == 0x2F:
        ab, cd, ef, gh = source[21:25]
        width = 1 + ((cd & 0x3F) << 8) + ab
        height = 1 + ((gh & 0xF) << 10) + (ef << 2) + (cd >> 6)
        return (width, height)
    _debug.logic(
        "image.webp_size_unreadable",
        chunk=source[12:16].hex(),
        source_bytes=len(source),
    )
    msg = "This file could not be decoded as an image file."
    raise ImageDecodeError(msg)


def _decoded_image_size(base64_source: bytes | str) -> tuple[int, int] | None:
    return ImageProcess(base64.b64decode(base64_source), verify_resolution=False).size


def is_image_size_above(
    base64_source_1: bytes | str | None, base64_source_2: bytes | str | None
) -> bool:
    if not base64_source_1 or not base64_source_2:
        return False
    source = _decoded_image_size(base64_source_1)
    if source is None:
        return False
    target = _decoded_image_size(base64_source_2)
    if target is None:
        return False
    return source[0] > target[0] or source[1] > target[1]


def image_guess_size_from_field_name(field_name: str) -> tuple[int, int]:
    if field_name == "image":
        return (1024, 1024)
    if field_name.startswith("x_"):
        return (0, 0)
    try:
        suffix = int(field_name.rsplit("_", 1)[-1])
    except ValueError:
        return 0, 0

    if suffix < 16:
        return (0, 0)

    return (suffix, suffix)
