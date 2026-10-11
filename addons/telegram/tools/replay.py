import hashlib
import json
import logging
import threading

_logger = logging.getLogger(__name__)

_state = threading.local()


def _payload_fingerprint(payload) -> str:
    try:
        blob = json.dumps(payload, sort_keys=True, default=str)
    except TypeError, ValueError:
        blob = repr(payload)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def begin_update(scope_key) -> None:
    if getattr(_state, "scope_key", None) != scope_key:
        _state.scope_key = scope_key
        _state.calls = {}
    _state.sequence = 0
    _state.memos = {}


def end_update() -> None:
    _state.scope_key = None
    _state.calls = {}
    _state.memos = {}
    _state.sequence = 0


def remember(kind: str, payload, factory):
    if getattr(_state, "scope_key", None) is None:
        return factory()

    sequence = getattr(_state, "sequence", 0)
    _state.sequence = sequence + 1
    key = (sequence, kind, _payload_fingerprint(payload))

    calls = _state.calls
    if key in calls:
        _logger.info(
            "Replay guard: %s #%s already delivered for this update, "
            "returning the recorded answer instead of calling Telegram again",
            kind,
            sequence,
        )
        return calls[key]

    result = factory()
    calls[key] = result
    return result


def memo(key, factory):
    if getattr(_state, "scope_key", None) is None:
        return factory()

    cached = getattr(_state, "memos", None)
    if cached is None:
        cached = _state.memos = {}
    if key not in cached:
        cached[key] = factory()
    return cached[key]


def begin_callback():
    _state.answered = set()
    return _state.answered


def note_callback_answered(callback_query_id) -> None:
    answered = getattr(_state, "answered", None)
    if answered is not None:
        answered.add(callback_query_id)
