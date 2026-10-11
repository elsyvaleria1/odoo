import binascii
import hashlib
import hmac
import os
import re
from base64 import b64decode, b64encode
from collections.abc import Iterable

from odoo.libs.debug_log import DebugLog

__all__ = ["HASH_PREFIX", "CryptContext", "pbkdf2_sha512_hash"]

_debug = DebugLog(__name__)

_DEFAULT_ROUNDS = 600_000
_MAX_ROUNDS = 10_000_000
_SALT_SIZE = 16
_HASH_SIZE = 64
HASH_PREFIX = "$pbkdf2-sha512$"
_MCF_RE = re.compile(r"^\$pbkdf2-sha512\$(\d+)\$([^$]+)\$([^$]+)$")
_FOREIGN_HASH_RE = re.compile(
    r"""
    \$(?:1|2[abxy]?|3|5|6|7|y|gy|apr1|sha1|scrypt|bcrypt-sha256|p5k2|scram
      |md5(?:,rounds=[0-9]+)?|argon2(?:i|d|id)|pbkdf2(?:-sha(?:1|256|512))?)
    \$[./A-Za-z0-9=,+_-]*\$[./A-Za-z0-9$=,+_-]+\Z
  | (?:pbkdf2_sha(?:1|256)|sha1|md5|argon2|bcrypt(?:_sha256)?|scrypt)
    \$[./A-Za-z0-9=,+_-]*\$[./A-Za-z0-9$=,+_-]+\Z
  | \{(?:S?SHA(?:256|384|512)?|S?MD5|CRYPT|PKCS5S2)\}[./A-Za-z0-9$+=]+\Z
  | \$[PH]\$[./A-Za-z0-9]{31}\Z
  | \$S\$[./A-Za-z0-9]{52}\Z
    """,
    re.VERBOSE,
)
_HASHING = "pbkdf2_sha512"
_SCHEMES = (_HASHING, "plaintext")


def _ab64_encode(data: bytes) -> str:
    return b64encode(data).rstrip(b"=").replace(b"+", b".").decode("ascii")


def _ab64_decode(data: str) -> bytes:
    b = data.replace(".", "+").encode("ascii")
    b += b"=" * (-len(b) % 4)
    return b64decode(b)


def _encode(password: str) -> bytes:
    try:
        return password.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("a password must be encodable as UTF-8") from error


def _pbkdf2_sha512(password: bytes, salt: bytes, rounds: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha512", password, salt, rounds, dklen=_HASH_SIZE)


def _check_rounds(rounds: object) -> int:
    if not isinstance(rounds, int) or isinstance(rounds, bool):
        raise TypeError(f"pbkdf2_sha512__rounds must be an int, got {rounds!r}")
    if not 0 < rounds <= _MAX_ROUNDS:
        raise ValueError(f"pbkdf2_sha512__rounds must be in (0, {_MAX_ROUNDS}]")
    return rounds


def _scheme_names(value: object, what: str, known: Iterable[str]) -> list[str]:
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list | tuple | set) or not all(
        isinstance(name, str) for name in names
    ):
        raise TypeError(f"{what} must be a sequence of scheme names, got {value!r}")
    unknown = sorted(set(names).difference(known))
    if unknown:
        raise ValueError(f"{what} names unknown schemes {unknown}")
    return list(names)


def _format_hash(rounds: int, salt: bytes, checksum: bytes) -> str:
    return f"{HASH_PREFIX}{rounds}${_ab64_encode(salt)}${_ab64_encode(checksum)}"


def _parse_hash(hash_str: str) -> tuple[int, bytes, bytes] | None:
    m = _MCF_RE.match(hash_str)
    if not m:
        return None
    try:
        rounds = int(m.group(1))
        if not 0 < rounds <= _MAX_ROUNDS:
            return None
        return rounds, _ab64_decode(m.group(2)), _ab64_decode(m.group(3))
    except binascii.Error, ValueError:
        return None


def pbkdf2_sha512_hash(password: str, rounds: int = _DEFAULT_ROUNDS) -> str:
    rounds = _check_rounds(rounds)
    encoded = _encode(password)
    salt = os.urandom(_SALT_SIZE)
    with _debug.perf("password.hash", rounds=rounds):
        checksum = _pbkdf2_sha512(encoded, salt, rounds)
    return _format_hash(rounds, salt, checksum)


class CryptContext:
    def __init__(
        self,
        schemes: list[str] | None = None,
        *,
        deprecated: list[str] | None = None,
        pbkdf2_sha512__rounds: int = _DEFAULT_ROUNDS,
    ) -> None:
        self._schemes = (
            _scheme_names(schemes, "schemes", _SCHEMES) if schemes else [_HASHING]
        )
        if self._schemes[0] != _HASHING:
            raise ValueError(
                f"the first scheme must be {_HASHING!r}, the one hash() writes"
            )
        self._deprecated = (
            set(_scheme_names(deprecated, "deprecated", [*self._schemes, "auto"]))
            if deprecated
            else set()
        )
        if _HASHING in self._deprecated:
            raise ValueError(
                f"{_HASHING!r} is the scheme hash() writes and cannot be deprecated"
            )
        self._rounds = _check_rounds(pbkdf2_sha512__rounds)

    def hash(self, password: str) -> str:
        return pbkdf2_sha512_hash(password, self._rounds)

    def is_password_valid(self, password: str, hash_str: str) -> bool:
        try:
            encoded = _encode(password)
        except ValueError:
            _debug.logic("password.verify", unencodable=True)
            return False
        parsed = _parse_hash(hash_str)
        if parsed:
            rounds, salt, expected = parsed
            with _debug.perf("password.verify", scheme=_HASHING, rounds=rounds):
                actual = _pbkdf2_sha512(encoded, salt, rounds)
            return hmac.compare_digest(actual, expected)
        scheme = self.identify(hash_str)
        if scheme == _HASHING:
            _debug.logic("password.verify", scheme=_HASHING, malformed=True)
            return False
        if scheme == "unknown":
            _debug.logic("password.verify", scheme="unknown", accepted=False)
            return False
        if "plaintext" in self._schemes:
            _debug.logic("password.verify", scheme="plaintext", accepted=True)
            return hmac.compare_digest(encoded, hash_str.encode("utf-8"))
        _debug.logic("password.verify", scheme="plaintext", accepted=False)
        return False

    def match_and_update(self, password: str, hash_str: str) -> tuple[bool, str | None]:
        if not self.is_password_valid(password, hash_str):
            return False, None

        needs_update = False
        scheme = self.identify(hash_str)

        if self._deprecated:
            if "auto" in self._deprecated:
                if scheme != self._schemes[0]:
                    needs_update = True
            elif scheme in self._deprecated:
                needs_update = True

        if scheme == _HASHING and not needs_update:
            parsed = _parse_hash(hash_str)
            if parsed and parsed[0] != self._rounds:
                needs_update = True

        _debug.logic(
            "password.match_and_update",
            scheme=scheme,
            deprecated=scheme in self._deprecated or "auto" in self._deprecated,
            needs_update=needs_update,
            rounds=self._rounds,
        )
        replacement = self.hash(password) if needs_update else None
        return True, replacement

    def identify(self, hash_str: str) -> str:
        if hash_str and hash_str.startswith(HASH_PREFIX):
            return _HASHING
        if _FOREIGN_HASH_RE.match(hash_str or ""):
            return "unknown"
        return "plaintext"
