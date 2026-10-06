from __future__ import annotations

import io
from fractions import Fraction

ASS_HEADER = (
    b"[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
    b"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def build_recording(
    seconds: int = 3,
    *,
    video: bool = True,
    audio: bool = True,
    subtitles: tuple[tuple[float, float, str], ...] = (),
) -> bytes:
    import av
    import numpy as np

    out = io.BytesIO()
    with av.open(out, "w", format="matroska") as container:
        picture = container.add_stream("mpeg4", rate=5) if video else None
        if picture is not None:
            picture.width, picture.height, picture.pix_fmt = 64, 48, "yuv420p"
        sound = (
            container.add_stream("libopus", rate=48000, layout="mono")
            if audio
            else None
        )
        captions = container.add_stream("ass") if subtitles else None
        if captions is not None:
            captions.codec_context.extradata = ASS_HEADER
            captions.time_base = Fraction(1, 1000)
        if picture is not None:
            for index in range(seconds * 5):
                shade = np.full((48, 64, 3), (index * 20) % 255, dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(shade, format="rgb24")
                frame.pts = index
                container.mux(picture.encode(frame))
            container.mux(picture.encode(None))
        if sound is not None:
            wave = (
                0.2 * np.sin(2 * np.pi * 440 * np.arange(48000 * seconds) / 48000)
            ).astype(np.float32)
            for offset in range(0, len(wave), 960):
                frame = av.AudioFrame.from_ndarray(
                    wave[offset : offset + 960].reshape(1, -1),
                    format="flt",
                    layout="mono",
                )
                frame.sample_rate = 48000
                frame.pts = offset
                container.mux(sound.encode(frame))
            container.mux(sound.encode(None))
        for order, (start, end, text) in enumerate(subtitles):
            packet = av.Packet(f"{order},0,Default,,0,0,0,,{text}".encode())
            packet.stream = captions
            packet.time_base = Fraction(1, 1000)
            packet.pts = packet.dts = int(start * 1000)
            packet.duration = int((end - start) * 1000)
            container.mux(packet)
    return out.getvalue()


def build_container(
    format: str,
    video_codec: str,
    audio_codec: str,
    subtitle_codec: str,
    subtitles: tuple[tuple[float, float, str], ...],
    seconds: int = 3,
) -> bytes:
    import av
    import numpy as np
    from av.subtitles.subtitle import SubtitleSet

    out = io.BytesIO()
    with av.open(out, "w", format=format) as container:
        picture = container.add_stream(video_codec, rate=5)
        picture.width, picture.height, picture.pix_fmt = 64, 48, "yuv420p"
        sound = container.add_stream(audio_codec, rate=48000, layout="mono")
        captions = container.add_stream(subtitle_codec)
        captions.codec_context.subtitle_header = ASS_HEADER
        captions.time_base = Fraction(1, 1000)
        for index in range(seconds * 5):
            shade = np.full((48, 64, 3), (index * 20) % 255, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(shade, format="rgb24")
            frame.pts = index
            container.mux(picture.encode(frame))
        container.mux(picture.encode(None))
        size = sound.codec_context.frame_size or 960
        wave = (
            0.2 * np.sin(2 * np.pi * 440 * np.arange(48000 * seconds) / 48000)
        ).astype(np.float32)
        for offset in range(0, len(wave) - size + 1, size):
            frame = av.AudioFrame.from_ndarray(
                wave[offset : offset + size].reshape(1, -1), format="flt", layout="mono"
            )
            frame.sample_rate = 48000
            frame.pts = offset
            container.mux(sound.encode(frame))
        container.mux(sound.encode(None))
        for order, (start, end, text) in enumerate(subtitles):
            start_ms, end_ms = round(start * 1000), round(end * 1000)
            packet = captions.codec_context.encode_subtitle(
                SubtitleSet.create(
                    f"{order},0,Default,,0,0,0,,{text}".encode(), 0, end_ms - start_ms
                )
            )
            packet.stream = captions
            packet.time_base = Fraction(1, 1000)
            packet.pts = packet.dts = start_ms
            packet.duration = end_ms - start_ms
            container.mux(packet)
    return out.getvalue()


def build_audio_with_cover(seconds: int = 1) -> bytes:
    import av
    import numpy as np

    out = io.BytesIO()
    with av.open(out, "w", format="mp4") as container:
        cover = container.add_stream("mjpeg", rate=1)
        cover.width = cover.height = 32
        cover.pix_fmt = "yuvj420p"
        cover.disposition = av.stream.Disposition.attached_pic
        sound = container.add_stream("aac", rate=48000, layout="mono")
        still = av.VideoFrame.from_ndarray(
            np.full((32, 32, 3), 200, dtype=np.uint8), format="rgb24"
        )
        still.pts = 0
        container.mux(cover.encode(still))
        container.mux(cover.encode(None))
        size = sound.codec_context.frame_size
        wave = np.zeros(48000 * seconds, dtype=np.float32)
        for offset in range(0, len(wave) - size + 1, size):
            frame = av.AudioFrame.from_ndarray(
                wave[offset : offset + size].reshape(1, -1), format="flt", layout="mono"
            )
            frame.sample_rate = 48000
            frame.pts = offset
            container.mux(sound.encode(frame))
        container.mux(sound.encode(None))
    return out.getvalue()
