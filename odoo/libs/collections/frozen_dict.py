__all__ = ["FrozenList", "frozendict"]

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from typing import Any, NoReturn, Self, override


class FrozenList[T](list[T]):
    # A list nothing can change, so it hashes like the tuple of its items: a
    # frozendict holding one caches its hash, which one holding a list never
    # may. Being a list, it still concatenates with lists, compares equal to
    # them, and reads as one to json, safe_eval and isinstance; what + * and
    # slicing return are plain lists the caller may change.
    __slots__ = ()

    def __new__(cls, iterable: Iterable[T] = (), /) -> Self:
        self = super().__new__(cls)
        list.extend(self, iterable)
        return self

    def __init__(self, iterable: Iterable[T] = (), /) -> None:
        pass

    def __hash__(self) -> int:  # type: ignore[override]
        return hash(tuple(self))

    def __reduce__(self) -> tuple[type[Self], tuple[list[T]]]:
        return (type(self), (list(self),))

    def _refuse(self, operation: str) -> NoReturn:
        msg = f"'{type(self).__name__}' object does not support {operation}"
        raise TypeError(msg)

    @override
    def __setitem__(self, key: Any, value: Any, /) -> NoReturn:
        self._refuse("item assignment")

    @override
    def __delitem__(self, key: Any, /) -> NoReturn:
        self._refuse("item deletion")

    @override
    def __iadd__(self, value: Iterable[T], /) -> NoReturn:  # type: ignore[override]
        self._refuse("+=")

    @override
    def __imul__(self, value: Any, /) -> NoReturn:
        self._refuse("*=")

    @override
    def append(self, value: T, /) -> NoReturn:
        self._refuse("append")

    @override
    def extend(self, values: Iterable[T], /) -> NoReturn:
        self._refuse("extend")

    @override
    def insert(self, index: Any, value: T, /) -> NoReturn:
        self._refuse("insert")

    @override
    def remove(self, value: T, /) -> NoReturn:
        self._refuse("remove")

    @override
    def pop(self, index: Any = -1, /) -> NoReturn:
        self._refuse("pop")

    @override
    def clear(self) -> NoReturn:
        self._refuse("clear")

    @override
    def sort(self, *args: Any, **kwargs: Any) -> NoReturn:
        self._refuse("sort")

    @override
    def reverse(self) -> NoReturn:
        self._refuse("reverse")


def freehash(arg: Any) -> int:
    try:
        return hash(arg)
    except TypeError:
        return hash(_freeze(arg, set(), None))


def _freeze(arg: Any, path: set[int], mutable: list[bool] | None) -> Any:
    # Maps a value to a hashable one that compares equal whenever the values compare
    # equal: a set freezes to the frozenset it equals, a tuple holding a dict to the
    # tuple holding the equal frozendict's frozen form, so == implies equal hashes.
    if type(arg) in _SCALARS:
        return arg
    if isinstance(arg, frozendict):
        if getattr(arg, "_hash", None) is not None:
            return arg
    elif isinstance(arg, (tuple, frozenset, FrozenList)):
        # a tuple, frozenset or FrozenList hashes even when it holds a frozendict over a
        # list, so its items are walked: trusting its hash would cache one the list can
        # outlive. Being immutable, it closes no cycle without a mutable value that marks
        # the path.
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
        # A value met again on its own path closes a cycle. Equal structures close it at the
        # same point, so a constant keeps them hashing equal; a cycle runs through a mutable
        # value, so no frozendict on it may cache a hash the cycle's breaking would change.
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
                # a hash over an unhashable value would outlive a change to that value; with
                # none below there is no cycle either, so this form is path-independent
                object.__setattr__(arg, "_hash", hash(frozen))
            return frozen
        if isinstance(arg, AbstractSet):
            return frozenset(_freeze(item, path, mutable) for item in arg)
        if isinstance(arg, Iterable):
            return tuple(
                item if type(item) in _SCALARS else _freeze(item, path, mutable)
                for item in arg
            )
        # an unhashable value compares by its own __eq__, which a hash cannot see into
        return _OPAQUE
    finally:
        path.discard(marker)


# the values a context mostly holds; hashed in place instead of through a call
_SCALARS = frozenset({str, int, bool, float, type(None), bytes})
_CYCLE = 0
_OPAQUE = 1


class frozendict[K, T](dict[K, T]):
    __slots__ = ("_hash",)

    _hash: int

    def __delitem__(self, key: K) -> NoReturn:
        msg = "'__delitem__' not supported on frozendict"
        raise NotImplementedError(msg)

    def __setitem__(self, key: K, val: T) -> NoReturn:
        msg = "'__setitem__' not supported on frozendict"
        raise NotImplementedError(msg)

    def clear(self) -> NoReturn:
        msg = "'clear' not supported on frozendict"
        raise NotImplementedError(msg)

    def pop(self, key: K, default: T | None = None) -> NoReturn:  # type: ignore[override]
        msg = "'pop' not supported on frozendict"
        raise NotImplementedError(msg)

    def popitem(self) -> NoReturn:
        msg = "'popitem' not supported on frozendict"
        raise NotImplementedError(msg)

    def setdefault(self, key: K, default: T | None = None) -> NoReturn:
        msg = "'setdefault' not supported on frozendict"
        raise NotImplementedError(msg)

    def update(self, *args: Any, **kwargs: Any) -> NoReturn:
        msg = "'update' not supported on frozendict"
        raise NotImplementedError(msg)

    def __ior__(self, other: Any) -> NoReturn:  # type: ignore[misc]
        msg = "'|=' not supported on frozendict"
        raise NotImplementedError(msg)

    @classmethod
    def fromkeys(cls, iterable: Iterable[Any], value: Any = None, /) -> Any:  # type: ignore[override]
        return cls(dict.fromkeys(iterable, value))

    def __reduce__(self) -> tuple[Any, tuple[type, dict[K, T]]]:
        return (_rebuild_frozendict, (type(self), dict(self)))

    def __hash__(self) -> int:  # type: ignore[override]
        try:
            return self._hash
        except AttributeError:
            return hash(_freeze(self, set(), [False]))


def _rebuild_frozendict[K, T](cls: type, items: dict[K, T]) -> Any:
    obj: dict[K, T] = dict.__new__(cls)
    dict.update(obj, items)
    return obj
