from base64 import urlsafe_b64decode


def base64url_to_bytes(val: str) -> bytes:
    return urlsafe_b64decode(f"{val}===")
