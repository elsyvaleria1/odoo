import hashlib
from collections.abc import Callable

from odoo.tools import hmac, is_hmac_valid, register_signed_scope

# A client subscribes to a channel by naming it, so a name a client can say is
# a name it can read. A string channel is therefore a capability: the server
# mints it for one audience, signed for one declared scope, and sends to the
# internal channel it stands for, which no client can name. A scope whose
# audience is people rather than devices also names its holder: the capability
# then resolves only for a subscriber that holder admits, so a name that leaves
# with someone who lost the right is worth nothing to them.
PREFIX = "bus"
TARGET = "bus.capability"

_SCOPES: dict[str, str] = {}
_HOLDERS: dict[str, Callable] = {}


def register_channel_scope(
    name: str, *, purpose: str, lifetime: str, holder: Callable | None = None
) -> str:
    """Declare a scope of bus channels: what a holder of one receives, and
    what revokes it (the key changes when its record's token is rotated, or
    never). ``holder(env, key)`` says whether the subscriber of ``env`` may
    hold the channel of ``key``; without it the capability is a bearer's.
    Returns the name, for the module to keep as its constant."""
    _check_part(name)
    _SCOPES[name] = register_signed_scope(
        f"bus.channel.{name}", purpose=purpose, lifetime=lifetime
    )
    if holder is not None:
        _HOLDERS[name] = holder
    return name


def channel_capability(env, scope: str, key) -> str:
    """The name a client subscribes with, for the audience of ``key``."""
    key = _check_part(str(key))
    return f"{PREFIX}:{scope}:{key}:{hmac(env, _signed_scope(scope), key)}"


def channel_target(env, scope: str, key) -> tuple:
    """The channel a server sends to; it receives what its capability's
    holders subscribed to."""
    _signed_scope(scope)
    return (env.cr.dbname, TARGET, scope, _check_part(str(key)))


def resolve_capability(env, name: str) -> tuple | None:
    """The channel ``name`` stands for, or None when it is no capability or
    not a valid one."""
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
    """A key part that changes with ``token``: a capability keyed with it is
    revoked when the token is rotated, and gives nothing of the token away."""
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
