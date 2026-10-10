from datetime import UTC, datetime
from typing import NamedTuple


class DeviceIngest(NamedTuple):
    created: object
    duplicates: int
    skipped_indexes: tuple[int, ...] = ()


def parse_epoch_or_iso(raw):
    if raw is None:
        return None
    text = str(raw)
    if text.isdecimal():
        value = int(text)
        if value > 10**12:
            value //= 1000
        try:
            return datetime.fromtimestamp(value, UTC).replace(tzinfo=None)
        except OverflowError, OSError, ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed
