from __future__ import annotations

import io
import re
from typing import Any

from .cues import Cue

__all__ = [
    "AUDIO_SAMPLE_RATE",
    "AUDIO_TRACK_MIMETYPE",
    "audio_track",
    "can_decode_media",
    "decode_audio",
    "keyframes",
    "media_duration_ms",
    "subtitle_cues",
]

AUDIO_SAMPLE_RATE = 16000
AUDIO_TRACK_MIMETYPE = "audio/ogg"

_ASS_OVERRIDE = re.compile(r"\{[^}]*\}")


def _av() -> Any:
    import av

    return av


def can_decode_media() -> bool:
    try:
        _av()
    except ImportError:
        return False
    return True


def _open(data: bytes) -> Any:
    return _av().open(io.BytesIO(data))


def _streams(container: Any, kind: str) -> list[Any]:
    # an MP4's cover art is a video stream of one still picture, not footage
    attached_pic = _av().stream.Disposition.attached_pic
    return [
        stream
        for stream in container.streams
        if stream.type == kind and not stream.disposition & attached_pic
    ]


def media_duration_ms(data: bytes) -> int:
    with _open(data) as container:
        if container.duration:
            return int(container.duration / 1000)
        seconds = max(
            (
                float(stream.duration * stream.time_base)
                for stream in container.streams
                if stream.duration and stream.time_base
            ),
            default=0.0,
        )
        return int(seconds * 1000)


def decode_audio(data: bytes, sample_rate: int = AUDIO_SAMPLE_RATE) -> Any:
    import numpy as np

    av = _av()
    chunks: list[Any] = []
    with _open(data) as container:
        streams = _streams(container, "audio")
        if not streams:
            return np.zeros(0, dtype=np.float32)
        resampler = av.AudioResampler(format="flt", layout="mono", rate=sample_rate)
        for frame in container.decode(streams[0]):
            chunks.extend(
                out.to_ndarray().reshape(-1) for out in resampler.resample(frame)
            )
        chunks.extend(out.to_ndarray().reshape(-1) for out in resampler.resample(None))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32)


def audio_track(data: bytes) -> bytes:
    """The first audio stream of a container, re-encoded as mono Ogg Opus.

    A vendor hears audio, not a video container: sending the whole file costs
    its capacity limit for bytes it never listens to.
    """
    av = _av()
    out = io.BytesIO()
    with _open(data) as source:
        streams = _streams(source, "audio")
        if not streams:
            return b""
        with av.open(out, "w", format="ogg") as target:
            encoded = target.add_stream("libopus", rate=48000, layout="mono")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
            for frame in source.decode(streams[0]):
                for piece in resampler.resample(frame):
                    target.mux(encoded.encode(piece))
            for piece in resampler.resample(None):
                target.mux(encoded.encode(piece))
            target.mux(encoded.encode(None))
    return out.getvalue()


def keyframes(data: bytes, every_s: float = 10.0, limit: int = 8) -> list[bytes]:
    images: list[bytes] = []
    with _open(data) as container:
        streams = _streams(container, "video")
        if not streams:
            return images
        streams[0].codec_context.skip_frame = "NONKEY"
        due = 0.0
        for frame in container.decode(streams[0]):
            at = float(frame.time or 0.0)
            if at + 1e-6 < due:
                continue
            buffer = io.BytesIO()
            frame.to_image().convert("RGB").save(buffer, format="JPEG", quality=80)
            images.append(buffer.getvalue())
            if len(images) >= limit:
                break
            due = at + every_s
    return images


def _subtitle_text(subtitle: Any) -> str:
    raw = getattr(subtitle, "dialogue", None) or getattr(subtitle, "text", None) or b""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    text = _ASS_OVERRIDE.sub("", text).replace("\\N", "\n").replace("\\n", "\n")
    return text.replace("\\h", " ").strip()


def subtitle_cues(data: bytes) -> list[Cue]:
    cues: list[Cue] = []
    with _open(data) as container:
        streams = _streams(container, "subtitle")
        if not streams:
            return cues
        stream = streams[0]
        for packet in container.demux(stream):
            if packet.pts is None:
                continue
            start = float(packet.pts * stream.time_base)
            end = start + float((packet.duration or 0) * stream.time_base)
            text = "\n".join(
                line for line in map(_subtitle_text, packet.decode()) if line
            )
            if text:
                cues.append(Cue(start=start, end=end, text=text))
    return cues
