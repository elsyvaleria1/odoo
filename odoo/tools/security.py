import base64
import datetime
import hashlib
import hmac as hmac_lib
import secrets
import time
import typing
import zlib
from dataclasses import dataclass
from typing import Any

from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.libs.secret import Secret as _Secret

if typing.TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping

    from odoo.api import Environment
    from odoo.orm._typing import BaseModel

_debug = DebugLog(__name__)


def consteq(presented: object, expected: object) -> bool:
    if isinstance(presented, _Secret):
        presented = presented.reveal_bytes()
    if isinstance(expected, _Secret):
        expected = expected.reveal_bytes()
    if isinstance(presented, str):
        presented = presented.encode()
    if isinstance(expected, str):
        expected = expected.encode()
    if not isinstance(presented, bytes) or not isinstance(expected, bytes):
        return False
    if not expected:
        return False
    return hmac_lib.compare_digest(presented, expected)


def hmac(
    env: Environment,
    scope: str,
    message: typing.Any,
    hash_function: Callable[[], Any] = hashlib.sha256,
) -> str:
    _check_registered(scope)

    config_parameter: Any = env(su=True)["ir.config_parameter"]
    secret = config_parameter.get_param("database.secret")
    if not secret:
        _debug.logic("security.hmac_secret_missing", scope=scope)
        raise ValueError(
            "The 'database.secret' configuration parameter is missing or empty; "
            "cannot compute a secure HMAC."
        )
    secret = str(secret)
    message = repr((scope, message))
    return hmac_lib.new(
        secret.encode(),
        message.encode(),
        hash_function,
    ).hexdigest()


@dataclass(frozen=True)
class SignedScope:
    name: str
    purpose: str
    lifetime: str


_SIGNED_SCOPES: dict[str, SignedScope] = {}


def register_signed_scope(name: str, *, purpose: str, lifetime: str) -> str:
    if not name or not purpose or not lifetime:
        raise ValueError("a signed scope states its name, purpose and lifetime")
    known = _SIGNED_SCOPES.get(name)
    if known and (known.purpose, known.lifetime) != (purpose, lifetime):
        raise ValueError(f"signed scope {name!r} is declared twice, differently")
    _SIGNED_SCOPES[name] = SignedScope(name, purpose, lifetime)
    return name


def signed_scopes() -> dict[str, SignedScope]:
    return dict(_SIGNED_SCOPES)


def _check_registered(scope: str) -> None:
    if scope not in _SIGNED_SCOPES:
        raise ValueError(f"signed scope {scope!r} was never registered")


def is_hmac_valid(
    env: Environment, scope: str, message: typing.Any, token: object
) -> bool:
    _check_registered(scope)
    if not isinstance(token, str) or not token or not token.isascii():
        return False
    return consteq(token, hmac(env, scope, message))


def hash_sign(
    env: Environment,
    scope: str,
    message_values: typing.Any,
    expiration_hours: float | None = None,
) -> str:
    if message_values is None:
        msg = "hash_sign() requires a message to sign"
        raise ValueError(msg)

    expiration_timestamp = (
        int(time.time() + expiration_hours * 3600) if expiration_hours else 0
    )
    message_strings = json_dumps(message_values)
    hash_value = hmac(
        env,
        scope,
        f"1:{message_strings}:{expiration_timestamp}",
        hash_function=hashlib.sha256,
    )
    token = (
        b"\x01"
        + expiration_timestamp.to_bytes(8, "little")
        + bytes.fromhex(hash_value)
        + message_strings.encode()
    )
    _debug.lifecycle(
        "security.hash_signed",
        scope=scope,
        expires=expiration_timestamp or None,
        message_bytes=len(message_strings),
    )
    return base64.urlsafe_b64encode(token).decode().rstrip("=")


def resolve_hash_signed(
    env: Environment, scope: str, payload: str
) -> typing.Any | None:
    _check_registered(scope)
    if not isinstance(payload, str):
        _debug.logic("security.hash_signed_rejected", scope=scope, reason="not_str")
        return None
    try:
        token = base64.urlsafe_b64decode(payload.encode() + b"===")
        if token[:1] != b"\x01":
            _debug.logic("security.hash_signed_rejected", scope=scope, reason="version")
            return None
        expiration_bytes, hash_value, message = (
            token[1:9],
            token[9:41].hex(),
            token[41:].decode(),
        )
    except ValueError, TypeError:
        _debug.logic("security.hash_signed_rejected", scope=scope, reason="malformed")
        return None
    expiration_timestamp = int.from_bytes(expiration_bytes, byteorder="little")
    hash_value_expected = hmac(
        env,
        scope,
        f"1:{message}:{expiration_timestamp}",
        hash_function=hashlib.sha256,
    )

    signed = consteq(hash_value, hash_value_expected)
    live = expiration_timestamp == 0 or time.time() < expiration_timestamp
    _debug.logic(
        "security.hash_signed_resolved",
        scope=scope,
        signed=signed,
        live=live,
        expires=expiration_timestamp or None,
    )
    if signed and live:
        return json_loads(message)
    return None


_SESSION_STATE_BINDING = ("db", "uid", "nonce")


def _session_state_nonce_key(scope: str) -> str:
    return f"signed_state_nonce.{scope}"


def issue_session_state(
    env: Environment,
    scope: str,
    session: MutableMapping[str, Any],
    claims: dict[str, Any],
    *,
    max_age_seconds: int,
) -> str:
    if max_age_seconds <= 0:
        raise ValueError("a session state lives a positive number of seconds")
    if clash := set(claims).intersection(_SESSION_STATE_BINDING):
        raise ValueError(f"a session state binds {sorted(clash)} itself")
    nonce = secrets.token_urlsafe(32)
    session[_session_state_nonce_key(scope)] = nonce
    bound = {**claims, "db": env.cr.dbname, "uid": env.uid, "nonce": nonce}
    return hash_sign(env, scope, bound, expiration_hours=max_age_seconds / 3600)


def consume_session_state(
    env: Environment,
    scope: str,
    session: MutableMapping[str, Any],
    state: object,
) -> dict[str, Any] | None:
    _check_registered(scope)
    expected_nonce = session.pop(_session_state_nonce_key(scope), None)
    if not isinstance(state, str):
        _debug.logic("security.session_state_rejected", scope=scope, reason="not_str")
        return None
    claims = resolve_hash_signed(env, scope, state)
    if not isinstance(claims, dict):
        _debug.logic(
            "security.session_state_rejected", scope=scope, reason="signature_or_expiry"
        )
        return None
    db, uid, nonce = (claims.pop(key, None) for key in _SESSION_STATE_BINDING)
    if not consteq(nonce, expected_nonce):
        reason = "consumed" if expected_nonce is None else "nonce"
        _debug.logic("security.session_state_rejected", scope=scope, reason=reason)
        return None
    if db != env.cr.dbname or uid != env.uid:
        _debug.logic("security.session_state_rejected", scope=scope, reason="bound")
        return None
    _debug.logic("security.session_state_consumed", scope=scope)
    return claims


def limited_field_access_token(
    record: BaseModel,
    field_name: str,
    timestamp: str | None = None,
    *,
    scope: str,
) -> str:
    record.check_singleton()
    if not timestamp:
        unique_str = repr((record._name, record.id, field_name))
        two_weeks = 1209600
        start_of_period = int(time.time()) // two_weeks * two_weeks
        adler32_max = 4294967295
        jitter = two_weeks * zlib.adler32(unique_str.encode()) // adler32_max
        timestamp = hex(start_of_period + 2 * two_weeks + jitter)
    token = hmac(
        record.env(su=True),
        scope,
        (record._name, record.id, field_name, timestamp),
    )
    return f"{token}o{timestamp}"


def is_valid_limited_field_access_token(
    record: BaseModel,
    field_name: str,
    access_token: str,
    *,
    scope: str,
) -> bool:
    _check_registered(scope)
    if not isinstance(access_token, str) or not access_token.isascii():
        _debug.logic(
            "security.field_token_rejected",
            model=record._name,
            field=field_name,
            reason="not_ascii_str",
        )
        return False
    *_, timestamp = access_token.rsplit("o", 1)
    try:
        expiration = datetime.datetime.fromtimestamp(int(timestamp, 16))
    except ValueError, OverflowError, OSError:
        _debug.logic(
            "security.field_token_rejected",
            model=record._name,
            field=field_name,
            reason="timestamp",
        )
        return False
    signed = consteq(
        access_token,
        limited_field_access_token(record, field_name, timestamp, scope=scope),
    )
    live = datetime.datetime.now() < expiration
    _debug.logic(
        "security.field_token_checked",
        model=record._name,
        record=record.id,
        field=field_name,
        signed=signed,
        live=live,
    )
    return signed and live
