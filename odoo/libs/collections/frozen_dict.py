__all__ = ["FrozenList", "frozendict"]

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from typing import Any, NoReturn, Self, overload, override


class FrozenList[T](list[T]):
    __slots__ = ()

    def __new__(cls, iterable: Iterable[T] = (), /) -> Self:
        self = super().__new__(cls)
        list.extend(self, iterable)
        return self

    def __init__(self, iterable: Iterable[T] = (), /) -> None:
        pass

    @override
    def __hash__(self) -> int:  # type: ignore[override]  # Immutable list deliberately restores hashing.
        return hash(tuple(self))

    @override
    def __reduce__(self) -> tuple[type[Self], tuple[list[T]]]:
        return (type(self), (list(self),))

    def _prepare_mutation_error(self, operation: str) -> TypeError:
        msg = f"'{type(self).__name__}' object does not support {operation}"
        return TypeError(msg)

    @override
    def __setitem__(self, key: Any, value: Any, /) -> NoReturn:
        raise self._prepare_mutation_error("item assignment")

    @override
    def __delitem__(self, key: Any, /) -> NoReturn:
        raise self._prepare_mutation_error("item deletion")

    @override
    def __iadd__(self, value: Iterable[T], /) -> NoReturn:  # type: ignore[override]  # Mutation is always refused, including widened lists.
        raise self._prepare_mutation_error("+=")

    @override
    def __imul__(self, value: Any, /) -> NoReturn:
        raise self._prepare_mutation_error("*=")

    @override
    def append(self, value: T, /) -> NoReturn:
        raise self._prepare_mutation_error("append")

    @override
    def extend(self, values: Iterable[T], /) -> NoReturn:
        raise self._prepare_mutation_error("extend")

    @override
    def insert(self, index: Any, value: T, /) -> NoReturn:
        raise self._prepare_mutation_error("insert")

    @override
    def remove(self, value: T, /) -> NoReturn:
        raise self._prepare_mutation_error("remove")

    @override
    def pop(self, index: Any = -1, /) -> NoReturn:
        raise self._prepare_mutation_error("pop")

    @override
    def clear(self) -> NoReturn:
        raise self._prepare_mutation_error("clear")

    @override
    def sort(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise self._prepare_mutation_error("sort")

    @override
    def reverse(self) -> NoReturn:
        raise self._prepare_mutation_error("reverse")


def freehash(arg: Any) -> int:
    try:
        return hash(arg)
    except TypeError:
        return hash(_freeze(arg, set(), None))


def _freeze(arg: Any, path: set[int], mutable: list[bool] | None) -> Any:
    if type(arg) in _SCALARS:
        return arg
    if isinstance(arg, frozendict):
        if getattr(arg, "_hash", None) is not None:
            return arg
    elif isinstance(arg, (tuple, frozenset, FrozenList)):
        items = []
        unchanged = True
        for item in arg:
            if type(item) not in _SCALARS:
                frozen = _freeze(item, path, mutable)
                if frozen is not item:
                    unchanged = False
                    item = frozen
            items.append(item)
        if unchanged:
            return arg
        return frozenset(items) if isinstance(arg, frozenset) else tuple(items)
    else:
        try:
            hash(arg)
        except TypeError:
            if mutable is not None:
                mutable[0] = True
        else:
            return arg
    if isinstance(arg, bytearray):
        return bytes(arg)
    marker = id(arg)
    if marker in path:
        if mutable is not None:
            mutable[0] = True
        return _CYCLE
    path.add(marker)
    try:
        if isinstance(arg, Mapping):
            if mutable is None or not isinstance(arg, frozendict):
                return frozenset(
                    (key, val if type(val) in _SCALARS else _freeze(val, path, mutable))
                    for key, val in arg.items()
                )
            own = [False]
            frozen = frozenset(
                (key, val if type(val) in _SCALARS else _freeze(val, path, own))
                for key, val in arg.items()
            )
            if own[0]:
                mutable[0] = True
            else:
                object.__setattr__(arg, "_hash", hash(frozen))
            return frozen
        if isinstance(arg, AbstractSet):
            return frozenset(_freeze(item, path, mutable) for item in arg)
        if isinstance(arg, Iterable):
            return tuple(
                item if type(item) in _SCALARS else _freeze(item, path, mutable)
                for item in arg
            )
        return _OPAQUE
    finally:
        path.discard(marker)


_SCALARS = frozenset({str, int, bool, float, type(None), bytes})
_CYCLE = 0
_OPAQUE = 1


class frozendict[K, T](dict[K, T]):
    __slots__ = ("_hash",)

    _hash: int

    @override
    def __delitem__(self, key: K) -> NoReturn:
        msg = "'__delitem__' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def __setitem__(self, key: K, val: T) -> NoReturn:
        msg = "'__setitem__' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def clear(self) -> NoReturn:
        msg = "'clear' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def pop(self, key: K, default: object = None) -> NoReturn:
        msg = "'pop' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def popitem(self) -> NoReturn:
        msg = "'popitem' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def setdefault(self, key: K, default: T | None = None) -> NoReturn:
        msg = "'setdefault' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def update(self, *args: Any, **kwargs: Any) -> NoReturn:
        msg = "'update' not supported on frozendict"
        raise NotImplementedError(msg)

    @override
    def __ior__(self, other: Any) -> NoReturn:
        msg = "'|=' not supported on frozendict"
        raise NotImplementedError(msg)

    @classmethod
    @overload
    def fromkeys[Key](
        cls, iterable: Iterable[Key], value: None = None, /
    ) -> frozendict[Key, None]: ...

    @classmethod
    @overload
    def fromkeys[Key, Value](
        cls, iterable: Iterable[Key], value: Value, /
    ) -> frozendict[Key, Value]: ...

    @classmethod
    @override
    def fromkeys(
        cls, iterable: Iterable[Any], value: Any = None, /
    ) -> frozendict[Any, Any]:
        return cls(dict.fromkeys(iterable, value))

    @override
    def __reduce__(self) -> tuple[object, tuple[type[Self], dict[K, T]]]:
        return (_rebuild_frozendict, (type(self), dict(self)))

    @override
    def __hash__(self) -> int:  # type: ignore[override]  # Immutable dictionary deliberately restores hashing.
        try:
            return self._hash
        except AttributeError:
            return hash(_freeze(self, set(), [False]))


def _rebuild_frozendict[K, T](
    cls: type[frozendict[K, T]], items: dict[K, T]
) -> frozendict[K, T]:
    obj: frozendict[K, T] = dict.__new__(cls)
    dict.update(obj, items)
    return obj
