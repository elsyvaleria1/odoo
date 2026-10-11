import secrets


def generate_user_handle() -> bytes:
    return secrets.token_bytes(64)
