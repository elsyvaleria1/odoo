import hashlib
import hmac
import time
from urllib.parse import parse_qsl

from odoo.tools import consteq

INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60
_CLOCK_SKEW_SECONDS = 60


def resolve_init_data(token, init_data, now=None, max_age=INIT_DATA_MAX_AGE_SECONDS):
    if not token or not init_data:
        return None
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed.items())
    )
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not consteq(received_hash, expected):
        return None
    try:
        auth_date = int(parsed.get("auth_date") or "")
    except ValueError:
        return None
    now = time.time() if now is None else now
    if auth_date > now + _CLOCK_SKEW_SECONDS or now - auth_date > max_age:
        return None
    return parsed
