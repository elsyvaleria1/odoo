import secrets

from odoo.libs.password import CryptContext

__all__ = ["INDEX_SIZE", "generate", "hash_key", "is_key_valid"]

INDEX_SIZE = 8
_CONTEXT = CryptContext(["pbkdf2_sha512"], pbkdf2_sha512__rounds=6000)


def generate() -> str:
    return secrets.token_hex(20)


def hash_key(key: str) -> str:
    return _CONTEXT.hash(key)


def is_key_valid(key: str, encoded: str) -> bool:
    return _CONTEXT.is_password_valid(key, encoded)
