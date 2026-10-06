import base64
import hashlib
import hmac
from collections import defaultdict
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


def compute_signature(
    auth_token: str, url: str, params: Iterable[tuple[str, object]]
) -> str:
    # Twilio sorts the parameter names and, under a repeated name, its distinct
    # values: a flattened dict keeps one value and signs something else
    values_by_name = defaultdict(set)
    for name, value in params:
        values_by_name[name].add(str(value))
    payload = url + "".join(
        name + value
        for name in sorted(values_by_name)
        for value in sorted(values_by_name[name])
    )
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def url_variants(url: str) -> list[str]:
    # with and without the scheme's default port: a proxy in front of Odoo
    # adds or drops it, and Twilio signed the URL as configured
    parts = urlsplit(url)
    default_port = DEFAULT_PORTS.get(parts.scheme)
    host = parts.hostname or ""
    if parts.port is None and default_port:
        other = f"{host}:{default_port}"
    elif parts.port == default_port:
        other = host
    else:
        return [url]
    return [url, urlunsplit(parts._replace(netloc=other))]


def is_signature_valid(
    auth_token: str,
    urls: Iterable[str],
    params: Iterable[tuple[str, str]],
    signature: str | None,
) -> bool:
    if not auth_token or not signature:
        return False
    try:
        presented = signature.encode("ascii")
    except UnicodeEncodeError:
        return False
    params = list(params)
    candidates = dict.fromkeys(variant for url in urls for variant in url_variants(url))
    return any(
        hmac.compare_digest(
            compute_signature(auth_token, candidate, params).encode(), presented
        )
        for candidate in candidates
    )
