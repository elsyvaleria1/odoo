from __future__ import annotations

import base64
import hashlib
import hmac
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["MASK", "Secret", "SecretRenderedError"]

MASK = "***REDACTED***"


class SecretRenderedError(TypeError):
    pass


class Secret:
    __slots__ = ("_value",)

    _value: str | bytes

    def __init__(self, value: str | bytes | Secret) -> None:
        if isinstance(value, Secret):
            value = value._value
        elif not isinstance(value, (str, bytes)):
            raise TypeError(
                f"a Secret wraps str or bytes, not {type(value).__name__}; "
                "Secret.of() takes an optional value"
            )
        self._value = value

    @classmethod
    def of(
        cls, value: str | bytes | Secret | typing.Literal[False] | None
    ) -> Secret | None:
        if not value:
            return None
        return cls(value)

    def reveal(self) -> str:
        value = self._value
        return value.decode() if isinstance(value, bytes) else value

    def reveal_bytes(self) -> bytes:
        value = self._value
        return value if isinstance(value, bytes) else value.encode()

    def map(self, fn: Callable[[str], str]) -> Secret:
        return Secret(fn(self.reveal()))

    def prefixed(self, prefix: str) -> Secret:
        return Secret(prefix + self.reveal())

    @staticmethod
    def basic(user: str, password: Secret | str) -> Secret:
        pair = f"{user}:{Secret(password).reveal()}".encode()
        return Secret("Basic " + base64.b64encode(pair).decode("ascii"))

    def matches(self, candidate: str | bytes | Secret) -> bool:
        if isinstance(candidate, Secret):
            presented = candidate.reveal_bytes()
        elif isinstance(candidate, str):
            presented = candidate.encode()
        elif isinstance(candidate, bytes):
            presented = candidate
        else:
            return False
        expected = self.reveal_bytes()
        if not expected or not presented:
            return False
        return hmac.compare_digest(presented, expected)

    def fingerprint(self) -> str:
        return hashlib.blake2s(self.reveal_bytes(), digest_size=8).hexdigest()

    def __repr__(self) -> str:
        return f"Secret({MASK!r})"

    def __str__(self) -> str:
        return MASK

    def __format__(self, format_spec: str) -> str:
        return MASK

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return hmac.compare_digest(self.reveal_bytes(), other.reveal_bytes())
        if isinstance(other, (str, bytes)):
            raise TypeError("a Secret is compared with .matches(), never ==")
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __reduce_ex__(self, protocol: typing.SupportsIndex) -> typing.NoReturn:
        raise TypeError("a Secret is never pickled")

    def __copy__(self) -> Secret:
        return self

    def __deepcopy__(self, memo: dict[int, typing.Any]) -> Secret:
        return self
