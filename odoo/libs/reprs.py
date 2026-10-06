__all__ = ["unquote"]


class unquote(str):
    __slots__ = ()

    def __repr__(self) -> str:
        return self
