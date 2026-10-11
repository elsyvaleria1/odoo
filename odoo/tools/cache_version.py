import typing
from functools import wraps

from odoo.libs.debug_log import DebugLog
from odoo.libs.hashing import cache_hash
from odoo.libs.json import OPT_SORT_KEYS, dumps_bytes

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from odoo.http import Request

__all__ = ["versioned", "versioned_dispatched", "versioned_envelope"]

_debug = DebugLog(__name__)


def _canonical_default(value: object) -> list | str:
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=_canonical_bytes)
    return str(value)


def _canonical_bytes(value: object) -> bytes:
    return dumps_bytes(value, option=OPT_SORT_KEYS, default=_canonical_default)


def _canonical_digest(value: object) -> str:
    return cache_hash(_canonical_bytes(value))


def _stamp[R](method: Callable[..., R], result: R) -> R:
    if isinstance(result, dict) and "__version" not in result:
        stamped = {**result, "__version": _canonical_digest(result)}
        _debug.perf.count(
            "cache_version.stamped", method=method.__qualname__, keys=len(stamped)
        )
        return typing.cast("R", stamped)
    return result


def versioned[**P, R](method: Callable[P, R]) -> Callable[P, R]:

    @wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return _stamp(method, method(*args, **kwargs))

    return wrapper


def versioned_dispatched[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    @wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = method(*args, **kwargs)
        try:
            from odoo.http import request
        except ModuleNotFoundError:
            return result
        if request and _is_dispatched_call(request, method):
            return _stamp(method, result)
        return result

    return wrapper


def versioned_envelope[**P, R](method: Callable[P, R]) -> Callable[P, R]:

    @wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        result = method(*args, **kwargs)
        try:
            from odoo.http import request
        except ModuleNotFoundError:
            return result
        if request and _is_dispatched_call(request, method):
            request.attempt_scratch.response_version = _canonical_digest(result)
            _debug.perf.count(
                "cache_version.envelope_stamped", method=method.__qualname__
            )
        return result

    return wrapper


def _is_dispatched_call(request: Request, method: Callable[..., object]) -> bool:
    params = getattr(request, "params", None) or {}
    return params.get("method") == method.__name__
