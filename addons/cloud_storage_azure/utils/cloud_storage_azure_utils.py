"""
This module is used to provide an azure.storage.blob.generate_blob_sas
compatible function for generating sas URLs for Azure Storage without
importing the azure.storage.blob library.
"""

import base64
import hashlib
import hmac
from datetime import date
from urllib.parse import quote

import requests
from lxml import etree

from odoo.exceptions import ValidationError
from odoo.libs import guarded_http, netguard

X_MS_VERSION = "2023-11-03"


def sign_string(key, string_to_sign):
    key = base64.b64decode(key.encode())
    string_to_sign = string_to_sign.encode()
    signed_hmac_sha256 = hmac.HMAC(key, string_to_sign, hashlib.sha256)
    digest = signed_hmac_sha256.digest()
    return base64.b64encode(digest).decode()


def _to_utc_datetime(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class QueryStringConstants:
    SIGNED_SIGNATURE = "sig"
    SIGNED_PERMISSION = "sp"
    SIGNED_START = "st"
    SIGNED_EXPIRY = "se"
    SIGNED_RESOURCE = "sr"
    SIGNED_IDENTIFIER = "si"
    SIGNED_IP = "sip"
    SIGNED_PROTOCOL = "spr"
    SIGNED_VERSION = "sv"
    SIGNED_CACHE_CONTROL = "rscc"
    SIGNED_CONTENT_DISPOSITION = "rscd"
    SIGNED_CONTENT_ENCODING = "rsce"
    SIGNED_CONTENT_LANGUAGE = "rscl"
    SIGNED_CONTENT_TYPE = "rsct"
    SIGNED_OID = "skoid"
    SIGNED_TID = "sktid"
    SIGNED_KEY_START = "skt"
    SIGNED_KEY_EXPIRY = "ske"
    SIGNED_KEY_SERVICE = "sks"
    SIGNED_KEY_VERSION = "skv"
    SIGNED_ENCRYPTION_SCOPE = "ses"

    SIGNED_AUTHORIZED_OID = "saoid"
    SIGNED_UNAUTHORIZED_OID = "suoid"
    SIGNED_CORRELATION_ID = "scid"


class BlobQueryStringConstants:
    SIGNED_TIMESTAMP = "snapshot"


class _BlobSharedAccessHelper:
    def __init__(self) -> None:
        self.query_dict = {}

    def _add_query(self, name, val) -> None:
        if val:
            self.query_dict[name] = str(val)

    def get_value_to_append(self, query):
        return_value = self.query_dict.get(query) or ""
        return return_value + "\n"

    def add_base(self, permission, expiry, start, ip, protocol, x_ms_version) -> None:
        if isinstance(start, date):
            start = _to_utc_datetime(start)

        if isinstance(expiry, date):
            expiry = _to_utc_datetime(expiry)

        self._add_query(QueryStringConstants.SIGNED_START, start)
        self._add_query(QueryStringConstants.SIGNED_EXPIRY, expiry)
        self._add_query(QueryStringConstants.SIGNED_PERMISSION, permission)
        self._add_query(QueryStringConstants.SIGNED_IP, ip)
        self._add_query(QueryStringConstants.SIGNED_PROTOCOL, protocol)
        self._add_query(QueryStringConstants.SIGNED_VERSION, x_ms_version)

    def add_resource(self, resource) -> None:
        self._add_query(QueryStringConstants.SIGNED_RESOURCE, resource)

    def add_id(self, policy_id) -> None:
        self._add_query(QueryStringConstants.SIGNED_IDENTIFIER, policy_id)

    def add_override_response_headers(
        self,
        cache_control,
        content_disposition,
        content_encoding,
        content_language,
        content_type,
    ) -> None:
        self._add_query(QueryStringConstants.SIGNED_CACHE_CONTROL, cache_control)
        self._add_query(
            QueryStringConstants.SIGNED_CONTENT_DISPOSITION, content_disposition
        )
        self._add_query(QueryStringConstants.SIGNED_CONTENT_ENCODING, content_encoding)
        self._add_query(QueryStringConstants.SIGNED_CONTENT_LANGUAGE, content_language)
        self._add_query(QueryStringConstants.SIGNED_CONTENT_TYPE, content_type)

    def add_resource_signature(
        self, account_name, account_key, path, user_delegation_key=None
    ) -> None:
        if path[0] != "/":
            path = "/" + path

        canonicalized_resource = "/blob/" + account_name + path + "\n"

        string_to_sign = (
            self.get_value_to_append(QueryStringConstants.SIGNED_PERMISSION)
            + self.get_value_to_append(QueryStringConstants.SIGNED_START)
            + self.get_value_to_append(QueryStringConstants.SIGNED_EXPIRY)
            + canonicalized_resource
        )

        if user_delegation_key is not None:
            self._add_query(
                QueryStringConstants.SIGNED_OID, user_delegation_key.signed_oid
            )
            self._add_query(
                QueryStringConstants.SIGNED_TID, user_delegation_key.signed_tid
            )
            self._add_query(
                QueryStringConstants.SIGNED_KEY_START, user_delegation_key.signed_start
            )
            self._add_query(
                QueryStringConstants.SIGNED_KEY_EXPIRY,
                user_delegation_key.signed_expiry,
            )
            self._add_query(
                QueryStringConstants.SIGNED_KEY_SERVICE,
                user_delegation_key.signed_service,
            )
            self._add_query(
                QueryStringConstants.SIGNED_KEY_VERSION,
                user_delegation_key.signed_version,
            )

            string_to_sign += (
                self.get_value_to_append(QueryStringConstants.SIGNED_OID)
                + self.get_value_to_append(QueryStringConstants.SIGNED_TID)
                + self.get_value_to_append(QueryStringConstants.SIGNED_KEY_START)
                + self.get_value_to_append(QueryStringConstants.SIGNED_KEY_EXPIRY)
                + self.get_value_to_append(QueryStringConstants.SIGNED_KEY_SERVICE)
                + self.get_value_to_append(QueryStringConstants.SIGNED_KEY_VERSION)
                + self.get_value_to_append(QueryStringConstants.SIGNED_AUTHORIZED_OID)
                + self.get_value_to_append(QueryStringConstants.SIGNED_UNAUTHORIZED_OID)
                + self.get_value_to_append(QueryStringConstants.SIGNED_CORRELATION_ID)
            )
        else:
            string_to_sign += self.get_value_to_append(
                QueryStringConstants.SIGNED_IDENTIFIER
            )

        string_to_sign += (
            self.get_value_to_append(QueryStringConstants.SIGNED_IP)
            + self.get_value_to_append(QueryStringConstants.SIGNED_PROTOCOL)
            + self.get_value_to_append(QueryStringConstants.SIGNED_VERSION)
            + self.get_value_to_append(QueryStringConstants.SIGNED_RESOURCE)
            + self.get_value_to_append(BlobQueryStringConstants.SIGNED_TIMESTAMP)
            + self.get_value_to_append(QueryStringConstants.SIGNED_ENCRYPTION_SCOPE)
            + self.get_value_to_append(QueryStringConstants.SIGNED_CACHE_CONTROL)
            + self.get_value_to_append(QueryStringConstants.SIGNED_CONTENT_DISPOSITION)
            + self.get_value_to_append(QueryStringConstants.SIGNED_CONTENT_ENCODING)
            + self.get_value_to_append(QueryStringConstants.SIGNED_CONTENT_LANGUAGE)
            + self.get_value_to_append(QueryStringConstants.SIGNED_CONTENT_TYPE)
        )

        if string_to_sign[-1] == "\n":
            string_to_sign = string_to_sign[:-1]

        self._add_query(
            QueryStringConstants.SIGNED_SIGNATURE,
            sign_string(
                account_key
                if user_delegation_key is None
                else user_delegation_key.value,
                string_to_sign,
            ),
        )

    def get_token(self):
        exclude = [BlobQueryStringConstants.SIGNED_TIMESTAMP]
        return "&".join(
            [
                f"{n}={quote(v)}"
                for n, v in self.query_dict.items()
                if v is not None and n not in exclude
            ]
        )


class UserDelegationKey:

    def __init__(self) -> None:
        self.signed_oid = None
        self.signed_tid = None
        self.signed_start = None
        self.signed_expiry = None
        self.signed_service = None
        self.signed_version = None
        self.value = None


def generate_blob_sas(
    account_name,
    container_name,
    blob_name,
    account_key=None,
    user_delegation_key=None,
    permission=None,
    expiry=None,
    start=None,
    policy_id=None,
    ip=None,
    protocol=None,
    cache_control=None,
    content_disposition=None,
    content_encoding=None,
    content_language=None,
    content_type=None,
):
    if not policy_id:
        if not expiry:
            raise ValueError(
                "'expiry' parameter must be provided when not using a stored access policy."
            )
        if not permission:
            raise ValueError(
                "'permission' parameter must be provided when not using a stored access policy."
            )
    if not user_delegation_key and not account_key:
        raise ValueError("Either user_delegation_key or account_key must be provided.")
    if isinstance(account_key, UserDelegationKey):
        user_delegation_key = account_key

    resource_path = container_name + "/" + blob_name

    sas = _BlobSharedAccessHelper()
    sas.add_base(permission, expiry, start, ip, protocol, X_MS_VERSION)
    sas.add_id(policy_id)

    resource = "b"
    sas.add_resource(resource)
    sas.add_override_response_headers(
        cache_control,
        content_disposition,
        content_encoding,
        content_language,
        content_type,
    )
    sas.add_resource_signature(
        account_name,
        account_key,
        resource_path,
        user_delegation_key=user_delegation_key,
    )

    return sas.get_token()


class ClientAuthenticationError(Exception):
    pass


def acquire_user_delegation_key(
    tenant_id,
    client_id,
    client_secret,
    account_name,
    key_start_time: date,
    key_expiry_time: date,
) -> UserDelegationKey:

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": f"https://{account_name}.blob.core.windows.net/.default",
        "grant_type": "client_credentials",
    }
    with guarded_http.guarded_session(netguard.PUBLIC_ONLY) as session:
        token_response = session.post(token_url, data=token_data, timeout=5)
    if token_response.status_code in (401, 403):
        raise ClientAuthenticationError(
            f"Failed to get access token: {token_response.content}"
        )
    if token_response.status_code != 200:
        raise ValidationError(f"Failed to get access token: {token_response.content}")
    access_token = token_response.json()["access_token"]

    key_data = f"""<?xml version='1.0' encoding='utf-8'?>
    <KeyInfo><Start>{_to_utc_datetime(key_start_time)}</Start><Expiry>{_to_utc_datetime(key_expiry_time)}</Expiry></KeyInfo>"""
    key_request_url = f"https://{account_name}.blob.core.windows.net/?restype=service&comp=userdelegationkey"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "x-ms-version": X_MS_VERSION,
        "Content-Type": "application/xml",
    }

    try:
        with guarded_http.guarded_session(netguard.PUBLIC_ONLY) as session:
            key_response = session.post(
                key_request_url, data=key_data, headers=headers, timeout=5
            )
    except requests.exceptions.ConnectionError:
        raise ValidationError(
            "Failed to get user delegation key: the account name may be incorrect"
        ) from None
    if key_response.status_code in (401, 403):
        raise ClientAuthenticationError(
            f"Failed to get user delegation key: {key_response.content}"
        )
    if key_response.status_code != 200:
        raise ValidationError(
            f"Failed to get user delegation key: {key_response.content}"
        )

    key_response_xml = etree.fromstring(key_response.content)
    user_delegation_key = UserDelegationKey()
    user_delegation_key.signed_oid = key_response_xml.findtext("SignedOid")
    user_delegation_key.signed_tid = key_response_xml.findtext("SignedTid")
    user_delegation_key.signed_start = key_response_xml.findtext("SignedStart")
    user_delegation_key.signed_expiry = key_response_xml.findtext("SignedExpiry")
    user_delegation_key.signed_service = key_response_xml.findtext("SignedService")
    user_delegation_key.signed_version = key_response_xml.findtext("SignedVersion")
    user_delegation_key.value = key_response_xml.findtext("Value")

    return user_delegation_key
