import base64
import hashlib
import logging
import os
from collections.abc import Mapping

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

__all__ = [
    "ENV_KEY",
    "SEALED_PREFIX",
    "TEST_RUN_KEY",
    "SealError",
    "is_configured",
    "is_sealed",
    "next_key_version",
    "old_key_versions",
    "protects",
    "rotated_environ",
    "seal",
    "unseal",
]

ENV_KEY = "ODOO_API_ENCRYPTION_KEY"
SEALED_PREFIX = "fernet:"

TEST_RUN_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(b"odoo test run without ODOO_API_ENCRYPTION_KEY").digest()
).decode()

_MAX_OLD_KEY_VERSION = 19
_MISSES_BEFORE_STOP = 2

_logger = logging.getLogger(__name__)
_reported_invalid: set[tuple[str, str]] = set()


class SealError(ValueError):
    pass


def old_key_versions(environ: Mapping[str, str] | None = None) -> list[int]:
    environ = os.environ if environ is None else environ
    versions = []
    misses = 0
    for version in range(1, _MAX_OLD_KEY_VERSION + 1):
        if environ.get(f"{ENV_KEY}_V{version}"):
            versions.append(version)
            misses = 0
        else:
            misses += 1
            if misses >= _MISSES_BEFORE_STOP:
                break
    return versions


def rotated_environ(
    key: str, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    entries = {ENV_KEY: key}
    current = environ.get(ENV_KEY)
    if current and current != key:
        version = next_key_version(environ)
        if version > _MAX_OLD_KEY_VERSION:
            raise SealError(
                f"{ENV_KEY}_V{version} would be past the {_MAX_OLD_KEY_VERSION} "
                f"predecessors unseal reads: what the key in force sealed could "
                f"not be opened"
            )
        entries[f"{ENV_KEY}_V{version}"] = current
    return entries


def next_key_version(environ: Mapping[str, str] | None = None) -> int:
    return max(old_key_versions(environ), default=0) + 1


def is_configured(environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    return bool(environ.get(ENV_KEY))


def protects(environ: Mapping[str, str] | None = None) -> bool:
    environ = os.environ if environ is None else environ
    return is_configured(environ) and environ[ENV_KEY] != TEST_RUN_KEY


def is_sealed(value: object) -> bool:
    return isinstance(value, str) and value.startswith(SEALED_PREFIX)


def _fernet(raw: str, name: str) -> Fernet:
    try:
        return Fernet(raw.encode())
    except (TypeError, ValueError) as error:
        raise SealError(f"{name} is not a valid Fernet key") from error


def seal(plaintext: str, environ: Mapping[str, str] | None = None) -> str:
    environ = os.environ if environ is None else environ
    if not is_configured(environ):
        raise SealError(f"{ENV_KEY} is not set: nothing can be sealed")
    token = _fernet(environ[ENV_KEY], ENV_KEY).encrypt(plaintext.encode())
    return SEALED_PREFIX + token.decode()


def unseal(value: str, environ: Mapping[str, str] | None = None) -> str:
    environ = os.environ if environ is None else environ
    if not is_sealed(value):
        raise SealError("the value is not sealed")
    names = []
    skipped = []
    keys = []
    if is_configured(environ):
        names.append(ENV_KEY)
        keys.append(_fernet(environ[ENV_KEY], ENV_KEY))
    for version in reversed(old_key_versions(environ)):
        name = f"{ENV_KEY}_V{version}"
        try:
            keys.append(_fernet(environ[name], name))
        except SealError:
            skipped.append(name)
            reported = (name, _fingerprint(environ[name]))
            if reported not in _reported_invalid:
                _reported_invalid.add(reported)
                _logger.warning("%s is not a valid Fernet key: skipped", name)
            continue
        names.append(name)
    invalid = ""
    if skipped:
        verb = "is" if len(skipped) == 1 else "are"
        noun = "a valid Fernet key" if len(skipped) == 1 else "valid Fernet keys"
        invalid = f"{', '.join(skipped)} {verb} not {noun}"
    if not keys:
        absent = f"{ENV_KEY} is not set" + (f" and {invalid}" if invalid else "")
        raise SealError(f"{absent}: the sealed value cannot be opened")
    try:
        return (
            MultiFernet(keys)
            .decrypt(value.removeprefix(SEALED_PREFIX).encode())
            .decode()
        )
    except InvalidToken as error:
        unread = f" ({invalid})" if invalid else ""
        raise SealError(
            f"no key among {', '.join(names)} opens the sealed value{unread}"
        ) from error


def _fingerprint(raw: str) -> str:
    return hashlib.sha256(raw.encode(errors="surrogatepass")).hexdigest()
