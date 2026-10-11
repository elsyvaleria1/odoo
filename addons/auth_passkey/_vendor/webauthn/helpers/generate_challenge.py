import secrets


def generate_challenge() -> bytes:
    return secrets.token_bytes(64)
