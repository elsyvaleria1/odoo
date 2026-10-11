import hashlib
from collections.abc import Callable

from odoo.tools import hmac, is_hmac_valid, register_signed_scope

PREFIX = "bus"
TARGET = "bus.capability"

_SCOPES: dict[str, str] = {}
_HOLDERS: dict[str, Callable] = {}


def register_channel_scope(
    name: str, *, purpose: str, lifetime: str, holder: Callable | None = None
) -> str:
    _check_part(name)
    _SCOPES[name] = register_signed_scope(
        f"bus.channel.{name}", purpose=purpose, lifetime=lifetime
    )
    if holder is not None:
        _HOLDERS[name] = holder
    return name


def channel_capability(env, scope: str, key) -> str:
    key = _check_part(str(key))
    return f"{PREFIX}:{scope}:{key}:{hmac(env, _signed_scope(scope), key)}"


def channel_target(env, scope: str, key) -> tuple:
    _signed_scope(scope)
    return (env.cr.dbname, TARGET, scope, _check_part(str(key)))


def resolve_capability(env, name: str) -> tuple | None:
    prefix, _sep, rest = name.partition(":")
    if prefix != PREFIX:
        return None
    scope, _sep, rest = rest.partition(":")
    key, _sep, signature = rest.rpartition(":")
    signed_scope = _SCOPES.get(scope)
    if not key or signed_scope is None:
        return None
    if not is_hmac_valid(env, signed_scope, key, signature):
        return None
    holder = _HOLDERS.get(scope)
    if holder is not None and not holder(env, key):
        return None
    return (env.cr.dbname, TARGET, scope, key)


def token_revision(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


def _signed_scope(scope: str) -> str:
    try:
        return _SCOPES[scope]
    except KeyError:
        raise ValueError(f"bus channel scope {scope!r} was never registered") from None


def _check_part(part: str) -> str:
    if not part or ":" in part:
        raise ValueError(
            f"a bus channel scope or key is non-empty, without ':': {part!r}"
        )
    return part
