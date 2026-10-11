from typing import NamedTuple

VOICE_NOTE_MIMETYPE = "audio/ogg"
VOICE_NOTE_NAME = "voice.ogg"
_MIMETYPES = {
    "oga": VOICE_NOTE_MIMETYPE,
    "ogg": VOICE_NOTE_MIMETYPE,
    "opus": VOICE_NOTE_MIMETYPE,
    "webm": "audio/webm",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
}
_EXTENSIONS = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/webm": "webm",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/flac": "flac",
}


class VoicePayload(NamedTuple):
    file_id: str
    filename: str
    duration: int


class Heard(NamedTuple):
    """What a voice message said, or why it was not heard: `no_audio` (the
    message carries none), `unheard` (nothing may hear it here), `too_long`,
    or `failed` (the download or the engine gave nothing)."""

    text: str | None = None
    failure: str | None = None
    duration: int = 0


def _extension(filename):
    stem, dot, extension = (filename or "").rpartition(".")
    return extension.lower() if dot and stem else ""


def mimetype_of(filename):
    return _MIMETYPES.get(_extension(filename), VOICE_NOTE_MIMETYPE)


def voice_payload(message):
    item = message.get("voice") or message.get("audio")
    if not item:
        document = message.get("document") or {}
        mimetype = (document.get("mime_type") or "").lower()
        if mimetype.startswith("audio/") or _extension(document.get("file_name")) in (
            _MIMETYPES
        ):
            item = document
    if not item or not item.get("file_id"):
        return None
    filename = item.get("file_name")
    if not filename:
        extension = _EXTENSIONS.get((item.get("mime_type") or "").lower())
        filename = f"audio.{extension}" if extension else VOICE_NOTE_NAME
    return VoicePayload(item["file_id"], filename, int(item.get("duration") or 0))
