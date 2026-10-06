from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, MutableMapping
from typing import Any

__all__ = [
    "is_available",
    "register_availability_gate",
    "remembered",
    "unregister_availability_gate",
]

_MEMO = "_availability_memo"

Gate = Callable[[Any, Mapping[str, Any]], bool]

_GATES: list[Gate] = []


def register_availability_gate(gate: Gate) -> Gate:
    if gate not in _GATES:
        _GATES.append(gate)
    return gate


def unregister_availability_gate(gate: Gate) -> None:
    while gate in _GATES:
        _GATES.remove(gate)


def is_available(component: Any, options: Mapping[str, Any]) -> bool:
    if not all(gate(component, options) for gate in _GATES):
        return False
    available = getattr(component, "available", None)
    return True if available is None else bool(available(options))


def remembered[T](
    options: Mapping[str, Any], key: Hashable, compute: Callable[[], T]
) -> T:
    # what a component works out to decide it is available and needs again to
    # read or write, worked out once: the memo lives in the document's options,
    # and a shallow copy of them (``write(value, **options)``) shares it
    if not isinstance(options, MutableMapping):
        return compute()
    memo = options.get(_MEMO)
    if memo is None:
        memo = options[_MEMO] = {}
    if key not in memo:
        memo[key] = compute()
    return memo[key]
