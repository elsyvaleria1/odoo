"""
This module is used to provide a google.cloud.storage._signing.generate_signed_url_v4
compatible function for generating signed URLs for Google Cloud Storage without
importing the google-cloud-storage library.
"""

import binascii
import collections
import datetime
import hashlib
import urllib

try:
    from google.oauth2 import service_account
except ImportError:
    service_account = None

DEFAULT_ENDPOINT = "https://storage.googleapis.com"
SEVEN_DAYS = 7 * 24 * 60 * 60
_EXPIRATION_TYPES = (int, datetime.datetime, datetime.timedelta)


def get_expiration_seconds_v4(expiration):
    if not isinstance(expiration, _EXPIRATION_TYPES):
        raise TypeError(
            "Expected an integer timestamp, datetime, or "
            "timedelta. Got %s" % type(expiration)
        )

    now = datetime.datetime.now(datetime.UTC)

    if isinstance(expiration, int):
        seconds = expiration

    if isinstance(expiration, datetime.datetime):
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=datetime.UTC)

        expiration -= now

    if isinstance(expiration, datetime.timedelta):
        seconds = int(expiration.total_seconds())

    if seconds > SEVEN_DAYS:
        raise ValueError(f"Max allowed expiration interval is seven days {SEVEN_DAYS}")

    return seconds


def get_v4_now_dtstamps() -> tuple:
    now = datetime.datetime.now(datetime.UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.date().strftime("%Y%m%d")
    return timestamp, datestamp


def get_canonical_headers(headers) -> tuple:
    if headers is None:
        headers = []
    elif isinstance(headers, dict):
        headers = list(headers.items())

    if not headers:
        return [], []

    normalized = collections.defaultdict(list)
    for key, val in headers:
        key = key.lower().strip()
        val = " ".join(val.split())
        normalized[key].append(val)

    ordered_headers = sorted((key, ",".join(val)) for key, val in normalized.items())

    canonical_headers = [f"{key}:{val}" for key, val in ordered_headers]
    return canonical_headers, ordered_headers


def generate_signed_url_v4(
    credentials,
    resource,
    expiration,
    api_access_endpoint=DEFAULT_ENDPOINT,
    method="GET",
    content_md5=None,
    content_type=None,
    response_type=None,
    response_disposition=None,
    generation=None,
    headers=None,
    query_parameters=None,
) -> str:
    expiration_seconds = get_expiration_seconds_v4(expiration)

    request_timestamp, datestamp = get_v4_now_dtstamps()

    client_email = credentials.signer_email

    credential_scope = f"{datestamp}/auto/storage/goog4_request"
    credential = f"{client_email}/{credential_scope}"

    if headers is None:
        headers = {}

    if content_type is not None:
        headers["Content-Type"] = content_type

    if content_md5 is not None:
        headers["Content-MD5"] = content_md5

    header_names = [key.lower() for key in headers]
    if "host" not in header_names:
        headers["Host"] = urllib.parse.urlparse(api_access_endpoint).netloc

    if method.upper() == "RESUMABLE":
        method = "POST"
        headers["x-goog-resumable"] = "start"

    canonical_headers, ordered_headers = get_canonical_headers(headers)
    canonical_header_string = "\n".join(canonical_headers) + "\n"
    signed_headers = ";".join([key for key, _ in ordered_headers])

    if query_parameters is None:
        query_parameters = {}
    else:
        query_parameters = {key: value or "" for key, value in query_parameters.items()}

    query_parameters["X-Goog-Algorithm"] = "GOOG4-RSA-SHA256"
    query_parameters["X-Goog-Credential"] = credential
    query_parameters["X-Goog-Date"] = request_timestamp
    query_parameters["X-Goog-Expires"] = expiration_seconds
    query_parameters["X-Goog-SignedHeaders"] = signed_headers

    if response_type is not None:
        query_parameters["response-content-type"] = response_type

    if response_disposition is not None:
        query_parameters["response-content-disposition"] = response_disposition

    if generation is not None:
        query_parameters["generation"] = generation

    canonical_query_string = urllib.parse.urlencode(
        query_parameters, quote_via=urllib.parse.quote
    )

    lowercased_headers = dict(ordered_headers)

    payload = lowercased_headers.get("x-goog-content-sha256", "UNSIGNED-PAYLOAD")

    canonical_elements = [
        method,
        resource,
        canonical_query_string,
        canonical_header_string,
        signed_headers,
        payload,
    ]
    canonical_request = "\n".join(canonical_elements)

    canonical_request_hash = hashlib.sha256(
        canonical_request.encode("ascii")
    ).hexdigest()

    string_elements = [
        "GOOG4-RSA-SHA256",
        request_timestamp,
        credential_scope,
        canonical_request_hash,
    ]
    string_to_sign = "\n".join(string_elements)

    signature_bytes = credentials.sign_bytes(string_to_sign.encode("ascii"))
    signature = binascii.hexlify(signature_bytes).decode("ascii")

    return f"{api_access_endpoint}{resource}?{canonical_query_string}&X-Goog-Signature={signature}"
