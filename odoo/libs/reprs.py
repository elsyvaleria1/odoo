from typing import override

__all__ = ["unquote"]


class unquote(str):
    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return self
