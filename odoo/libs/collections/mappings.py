__all__ = ["ConstantMapping", "DotDict", "ReadonlyDict", "submap"]

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, override


class ConstantMapping[T](Mapping[Any, T]):
    __slots__ = ["_value"]

    def __init__(self, val: T) -> None:
        self._value = val

    @override
    def __len__(self) -> int:
        return 0

    @override
    def __iter__(self) -> Iterator[Any]:
        return iter(())

    @override
    def __getitem__(self, item: Any) -> T:
        return self._value


class ReadonlyDict[K, T](Mapping[K, T]):
    __slots__ = ("_data__",)

    def __init__(self, data: Mapping[K, T]) -> None:
        self._data__ = dict(data)

    @override
    def __contains__(self, key: object) -> bool:
        return key in self._data__

    @override
    def __getitem__(self, key: K) -> T:
        return self._data__[key]

    @override
    def __len__(self) -> int:
        return len(self._data__)

    @override
    def __iter__(self) -> Iterator[K]:
        return iter(self._data__)


def submap[K, T](mapping: Mapping[K, T], keys: Iterable[K]) -> dict[K, T]:
    keys = frozenset(keys)
    return {key: mapping[key] for key in mapping if key in keys}


class DotDict(dict[str, Any]):
    def __getattr__(self, attrib: str) -> Any:
        if attrib.startswith("__") and attrib.endswith("__"):
            raise AttributeError(attrib)
        val = self.get(attrib)
        return DotDict(val) if isinstance(val, dict) else val
