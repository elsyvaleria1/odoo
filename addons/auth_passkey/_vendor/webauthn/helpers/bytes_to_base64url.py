from base64 import urlsafe_b64encode


def bytes_to_base64url(val: bytes) -> str:
    return urlsafe_b64encode(val).decode("utf-8").rstrip("=")
