import hashlib
from collections.abc import Buffer
from pathlib import Path
from typing import Protocol, runtime_checkable

try:
    from blake3 import blake3 as _blake3
except ImportError:
    _blake3 = None

__all__ = [
    "ALGO_TAG",
    "CONTENT_DIGEST_LEN",
    "CONTENT_DIGEST_MAX_LEN",
    "HAS_BLAKE3",
    "Hasher",
    "cache_hash",
    "content_hash",
    "content_hash_file",
    "prepare_cache_hasher",
    "prepare_content_hasher",
    "update_from_file",
]

HAS_BLAKE3 = _blake3 is not None

ALGO_TAG = "b3" if HAS_BLAKE3 else "s1"

_CONTENT_DIGEST_LEN_BY_TAG = {"s1": 40, "b3": 64}

CONTENT_DIGEST_LEN = _CONTENT_DIGEST_LEN_BY_TAG[ALGO_TAG]

CONTENT_DIGEST_MAX_LEN = 64

if CONTENT_DIGEST_LEN > CONTENT_DIGEST_MAX_LEN:
    raise RuntimeError(
        f"content digest is {CONTENT_DIGEST_LEN} hex chars but the schema "
        f"holds at most {CONTENT_DIGEST_MAX_LEN}: widen "
        "ir_attachment.checksum and migrate existing databases before "
        "switching to a longer algorithm"
    )

_FILE_CHUNK = 1 << 20


class Hasher(Protocol):
    def update(self, data: Buffer, /) -> object: ...

    def hexdigest(self) -> str: ...


@runtime_checkable
class _MmapHasher(Hasher, Protocol):
    def update_mmap(self, path: str, /) -> object: ...


def _prepare_blake3_hasher() -> _MmapHasher:
    hasher: _MmapHasher = _blake3(max_threads=1)
    return hasher


def prepare_content_hasher() -> Hasher:
    return (
        _prepare_blake3_hasher() if HAS_BLAKE3 else hashlib.sha1(usedforsecurity=False)
    )


def content_hash(data: bytes) -> str:
    data = data or b""
    if not HAS_BLAKE3:
        return hashlib.sha1(data, usedforsecurity=False).hexdigest()
    hasher = _prepare_blake3_hasher()
    hasher.update(data)
    return hasher.hexdigest()


def update_from_file(hasher: Hasher, path: str | Path) -> None:
    if isinstance(hasher, _MmapHasher):
        hasher.update_mmap(str(path))
        return
    with Path(path).open("rb") as fd:
        while chunk := fd.read(_FILE_CHUNK):
            hasher.update(chunk)


def content_hash_file(path: str | Path) -> str:
    hasher = prepare_content_hasher()
    update_from_file(hasher, path)
    return hasher.hexdigest()


def prepare_cache_hasher() -> Hasher:
    return _prepare_blake3_hasher() if HAS_BLAKE3 else hashlib.sha256()


def cache_hash(data: bytes) -> str:
    if not HAS_BLAKE3:
        return hashlib.sha256(data).hexdigest()
    hasher = _prepare_blake3_hasher()
    hasher.update(data)
    return hasher.hexdigest()
