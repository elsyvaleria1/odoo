from odoo.libs.json import loads as json_loads
from json.decoder import JSONDecodeError
from typing import Union

from .exceptions import InvalidAuthenticationResponse, InvalidJSONStructure
from .base64url_to_bytes import base64url_to_bytes
from .structs import (
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttachment,
    PublicKeyCredentialType,
)


def parse_authentication_credential_json(json_val: Union[str, dict]) -> AuthenticationCredential:
    if isinstance(json_val, str):
        try:
            json_val = json_loads(json_val)
        except JSONDecodeError:
            raise InvalidJSONStructure("Unable to decode credential as JSON")

    if not isinstance(json_val, dict):
        raise InvalidJSONStructure("Credential was not a JSON object")

    cred_id = json_val.get("id")
    if not isinstance(cred_id, str):
        raise InvalidJSONStructure("Credential missing required id")

    cred_raw_id = json_val.get("rawId")
    if not isinstance(cred_raw_id, str):
        raise InvalidJSONStructure("Credential missing required rawId")

    cred_response = json_val.get("response")
    if not isinstance(cred_response, dict):
        raise InvalidJSONStructure("Credential missing required response")

    response_client_data_json = cred_response.get("clientDataJSON")
    if not isinstance(response_client_data_json, str):
        raise InvalidJSONStructure("Credential response missing required clientDataJSON")

    response_authenticator_data = cred_response.get("authenticatorData")
    if not isinstance(response_authenticator_data, str):
        raise InvalidJSONStructure("Credential response missing required authenticatorData")

    response_signature = cred_response.get("signature")
    if not isinstance(response_signature, str):
        raise InvalidJSONStructure("Credential response missing required signature")

    cred_type = json_val.get("type")
    try:
        PublicKeyCredentialType(cred_type)
    except ValueError as cred_type_exc:
        raise InvalidJSONStructure("Credential had unexpected type") from cred_type_exc

    response_user_handle = cred_response.get("userHandle")
    if isinstance(response_user_handle, str):
        response_user_handle = base64url_to_bytes(response_user_handle)
    elif response_user_handle is not None:
        raise InvalidJSONStructure("Credential response had unexpected userHandle")

    cred_authenticator_attachment = json_val.get("authenticatorAttachment")
    if isinstance(cred_authenticator_attachment, str):
        try:
            cred_authenticator_attachment = AuthenticatorAttachment(cred_authenticator_attachment)
        except ValueError as cred_attachment_exc:
            raise InvalidJSONStructure(
                "Credential had unexpected authenticatorAttachment"
            ) from cred_attachment_exc
    else:
        cred_authenticator_attachment = None

    try:
        authentication_credential = AuthenticationCredential(
            id=cred_id,
            raw_id=base64url_to_bytes(cred_raw_id),
            response=AuthenticatorAssertionResponse(
                client_data_json=base64url_to_bytes(response_client_data_json),
                authenticator_data=base64url_to_bytes(response_authenticator_data),
                signature=base64url_to_bytes(response_signature),
                user_handle=response_user_handle,
            ),
            authenticator_attachment=cred_authenticator_attachment,
            type=PublicKeyCredentialType.PUBLIC_KEY,
        )
    except Exception as exc:
        raise InvalidAuthenticationResponse(
            "Could not parse authentication credential from JSON data"
        ) from exc

    return authentication_credential
