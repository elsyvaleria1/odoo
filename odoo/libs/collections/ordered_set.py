__all__ = ["FrozenOrderedSet", "LastOrderedSet", "OrderedSet"]

import itertools
from abc import abstractmethod
from collections.abc import (
    Iterable,
    Iterator,
    Mapping,
    MutableSet,
)
from collections.abc import (
    Set as AbstractSet,
)
from functools import reduce
from types import MappingProxyType
from typing import TYPE_CHECKING, Self, override


class _OrderedSetBase[T](AbstractSet[T]):
    __slots__ = ()
    _map: Mapping[T, None]

    @abstractmethod
    def __init__(self, elems: Iterable[T] = ()) -> None:
        pass

    @override
    def __contains__(self, elem: object) -> bool:
        return elem in self._map

    @override
    def __iter__(self) -> Iterator[T]:
        return iter(self._map)

    @override
    def __len__(self) -> int:
        return len(self._map)

    @override
    def __and__(self, other: Iterable[object]) -> Self:
        if not isinstance(other, Iterable):
            return NotImplemented
        members = other if isinstance(other, (AbstractSet, Mapping)) else set(other)
        return type(self)(elem for elem in self if elem in members)

    __rand__ = __and__

    if TYPE_CHECKING:

        @override
        def __sub__(self, other: AbstractSet[object]) -> Self: ...

    @override
    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self)!r})"


class FrozenOrderedSet[T](_OrderedSetBase[T]):
    __slots__ = ("_map",)

    if TYPE_CHECKING:
        # Set's implementations construct type(self); preserve the concrete type
        # while allowing unions and symmetric differences to widen element types.
        @override
        def __or__[U](self, other: AbstractSet[U]) -> FrozenOrderedSet[T | U]: ...
        @override
        def __xor__[U](self, other: AbstractSet[U]) -> FrozenOrderedSet[T | U]: ...

    def __init__(self, elems: Iterable[T] = ()) -> None:
        object.__setattr__(self, "_map", MappingProxyType(dict.fromkeys(elems)))

    @override
    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("FrozenOrderedSet is immutable")

    @override
    def __delattr__(self, name: str) -> None:
        raise TypeError("FrozenOrderedSet is immutable")

    @override
    def __hash__(self) -> int:
        return hash(frozenset(self._map))

    @override
    def __reduce__(self) -> tuple[type[Self], tuple[tuple[T, ...]]]:
        return type(self), (tuple(self),)


class OrderedSet[T](_OrderedSetBase[T], MutableSet[T]):
    __slots__ = ["_map"]

    if TYPE_CHECKING:

        @override
        def __or__[U](self, other: AbstractSet[U]) -> OrderedSet[T | U]: ...
        @override
        def __xor__[U](self, other: AbstractSet[U]) -> OrderedSet[T | U]: ...

    def __init__(self, elems: Iterable[T] = ()) -> None:
        self._map: dict[T, None] = dict.fromkeys(elems)

    @override
    def add(self, elem: T) -> None:
        self._map[elem] = None

    @override
    def discard(self, elem: T) -> None:
        self._map.pop(elem, None)

    def update(self, elems: Iterable[T]) -> None:
        self._map.update(zip(elems, itertools.repeat(None)))

    def difference_update(self, elems: Iterable[T]) -> None:
        _pop = self._map.pop
        for elem in elems:
            _pop(elem, None)

    def intersection(self, *others: Iterable[T]) -> Self:
        if not others:
            return self.copy()
        intersect = OrderedSet.__and__
        return reduce(intersect, others, self)

    def copy(self) -> Self:
        instance = object.__new__(type(self))
        instance._map = self._map.copy()
        return instance


class LastOrderedSet[T](OrderedSet[T]):
    __slots__ = ()

    def __init__(self, elems: Iterable[T] = ()) -> None:
        self._map = {}
        self.update(elems)

    @override
    def add(self, elem: T) -> None:
        self.discard(elem)
        super().add(elem)

    @override
    def update(self, elems: Iterable[T]) -> None:
        for elem in elems:
            self.add(elem)
