import hashlib
from dataclasses import dataclass, asdict
from typing import List, Mapping, Optional, Union

from ...webauthn.helpers import (
    aaguid_to_string,
    bytes_to_base64url,
    byteslike_to_bytes,
    decode_credential_public_key,
    parse_attestation_object,
    parse_client_data_json,
    parse_backup_flags,
    parse_registration_credential_json,
)
from ...webauthn.helpers.cose import COSEAlgorithmIdentifier
from ...webauthn.helpers.exceptions import InvalidRegistrationResponse
from ...webauthn.helpers.structs import (
    AttestationFormat,
    ClientDataType,
    CredentialDeviceType,
    PublicKeyCredentialType,
    RegistrationCredential,
    TokenBindingStatus,
)
from .formats.android_key import verify_android_key
from .formats.android_safetynet import verify_android_safetynet
from .formats.apple import verify_apple
from .formats.fido_u2f import verify_fido_u2f
from .formats.packed import verify_packed
from .formats.tpm import verify_tpm
from .generate_registration_options import default_supported_pub_key_algs


@dataclass
class VerifiedRegistration:

    credential_id: bytes
    credential_public_key: bytes
    sign_count: int
    aaguid: str
    fmt: AttestationFormat
    credential_type: PublicKeyCredentialType
    user_verified: bool
    attestation_object: bytes
    credential_device_type: CredentialDeviceType
    credential_backed_up: bool


expected_token_binding_statuses = [
    TokenBindingStatus.SUPPORTED,
    TokenBindingStatus.PRESENT,
]


def verify_registration_response(
    *,
    credential: Union[str, dict, RegistrationCredential],
    expected_challenge: bytes,
    expected_rp_id: str,
    expected_origin: Union[str, List[str]],
    require_user_verification: bool = False,
    supported_pub_key_algs: List[COSEAlgorithmIdentifier] = default_supported_pub_key_algs,
    pem_root_certs_bytes_by_fmt: Optional[Mapping[AttestationFormat, List[bytes]]] = None,
) -> VerifiedRegistration:
    if isinstance(credential, str) or isinstance(credential, dict):
        credential = parse_registration_credential_json(credential)

    verified = False

    if bytes_to_base64url(credential.raw_id) != credential.id:
        raise InvalidRegistrationResponse("id and raw_id were not equivalent")

    if credential.type != PublicKeyCredentialType.PUBLIC_KEY:
        raise InvalidRegistrationResponse(
            f'Unexpected credential type "{credential.type}", expected "public-key"'
        )

    response = credential.response

    client_data_bytes = byteslike_to_bytes(response.client_data_json)
    attestation_object_bytes = byteslike_to_bytes(response.attestation_object)

    client_data = parse_client_data_json(client_data_bytes)

    if client_data.type != ClientDataType.WEBAUTHN_CREATE:
        raise InvalidRegistrationResponse(
            f'Unexpected client data type "{client_data.type}", expected "{ClientDataType.WEBAUTHN_CREATE}"'
        )

    if expected_challenge != client_data.challenge:
        raise InvalidRegistrationResponse("Client data challenge was not expected challenge")

    if isinstance(expected_origin, str):
        if expected_origin != client_data.origin:
            raise InvalidRegistrationResponse(
                f'Unexpected client data origin "{client_data.origin}", expected "{expected_origin}"'
            )
    else:
        try:
            expected_origin.index(client_data.origin)
        except ValueError:
            raise InvalidRegistrationResponse(
                f'Unexpected client data origin "{client_data.origin}", expected one of {expected_origin}'
            )

    if client_data.token_binding:
        status = client_data.token_binding.status
        if status not in expected_token_binding_statuses:
            raise InvalidRegistrationResponse(
                f'Unexpected token_binding status of "{status}", expected one of "{",".join(expected_token_binding_statuses)}"'
            )

    attestation_object = parse_attestation_object(attestation_object_bytes)

    auth_data = attestation_object.auth_data

    expected_rp_id_hash = hashlib.sha256()
    expected_rp_id_hash.update(expected_rp_id.encode("utf-8"))
    expected_rp_id_hash_bytes = expected_rp_id_hash.digest()

    if auth_data.rp_id_hash != expected_rp_id_hash_bytes:
        raise InvalidRegistrationResponse("Unexpected RP ID hash")

    if not auth_data.flags.up:
        raise InvalidRegistrationResponse("User was not present during attestation")

    if require_user_verification and not auth_data.flags.uv:
        raise InvalidRegistrationResponse(
            "User verification is required but user was not verified during attestation"
        )

    if not auth_data.attested_credential_data:
        raise InvalidRegistrationResponse("Authenticator did not provide attested credential data")

    attested_credential_data = auth_data.attested_credential_data

    if not attested_credential_data.credential_id:
        raise InvalidRegistrationResponse("Authenticator did not provide a credential ID")

    if not attested_credential_data.credential_public_key:
        raise InvalidRegistrationResponse("Authenticator did not provide a credential public key")

    if not attested_credential_data.aaguid:
        raise InvalidRegistrationResponse("Authenticator did not provide an AAGUID")

    decoded_credential_public_key = decode_credential_public_key(
        attested_credential_data.credential_public_key
    )

    if decoded_credential_public_key.alg not in supported_pub_key_algs:
        raise InvalidRegistrationResponse(
            f'Unsupported credential public key alg "{decoded_credential_public_key.alg}", expected one of: {supported_pub_key_algs}'
        )

    pem_root_certs_bytes: List[bytes] = []
    if pem_root_certs_bytes_by_fmt:
        custom_certs = pem_root_certs_bytes_by_fmt.get(attestation_object.fmt)
        if custom_certs:
            pem_root_certs_bytes.extend(custom_certs)

    if attestation_object.fmt == AttestationFormat.NONE:
        any_att_stmt_fields_set = any(
            [field is not None for field in asdict(attestation_object.att_stmt).values()]
        )

        if any_att_stmt_fields_set:
            raise InvalidRegistrationResponse(
                "None attestation had unexpected attestation statement"
            )

        verified = True
    elif attestation_object.fmt == AttestationFormat.FIDO_U2F:
        verified = verify_fido_u2f(
            attestation_statement=attestation_object.att_stmt,
            client_data_json=client_data_bytes,
            rp_id_hash=auth_data.rp_id_hash,
            credential_id=attested_credential_data.credential_id,
            credential_public_key=attested_credential_data.credential_public_key,
            aaguid=attested_credential_data.aaguid,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    elif attestation_object.fmt == AttestationFormat.PACKED:
        verified = verify_packed(
            attestation_statement=attestation_object.att_stmt,
            attestation_object=attestation_object_bytes,
            client_data_json=client_data_bytes,
            credential_public_key=attested_credential_data.credential_public_key,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    elif attestation_object.fmt == AttestationFormat.TPM:
        verified = verify_tpm(
            attestation_statement=attestation_object.att_stmt,
            attestation_object=attestation_object_bytes,
            client_data_json=client_data_bytes,
            credential_public_key=attested_credential_data.credential_public_key,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    elif attestation_object.fmt == AttestationFormat.APPLE:
        verified = verify_apple(
            attestation_statement=attestation_object.att_stmt,
            attestation_object=attestation_object_bytes,
            client_data_json=client_data_bytes,
            credential_public_key=attested_credential_data.credential_public_key,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    elif attestation_object.fmt == AttestationFormat.ANDROID_SAFETYNET:
        verified = verify_android_safetynet(
            attestation_statement=attestation_object.att_stmt,
            attestation_object=attestation_object_bytes,
            client_data_json=client_data_bytes,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    elif attestation_object.fmt == AttestationFormat.ANDROID_KEY:
        verified = verify_android_key(
            attestation_statement=attestation_object.att_stmt,
            attestation_object=attestation_object_bytes,
            client_data_json=client_data_bytes,
            credential_public_key=attested_credential_data.credential_public_key,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    else:
        raise InvalidRegistrationResponse(
            f'Unsupported attestation type "{attestation_object.fmt}"'
        )

    if not verified:
        raise InvalidRegistrationResponse("Attestation statement could not be verified")

    parsed_backup_flags = parse_backup_flags(auth_data.flags)

    return VerifiedRegistration(
        credential_id=attested_credential_data.credential_id,
        credential_public_key=attested_credential_data.credential_public_key,
        sign_count=auth_data.sign_count,
        aaguid=aaguid_to_string(attested_credential_data.aaguid),
        fmt=attestation_object.fmt,
        credential_type=credential.type,
        user_verified=auth_data.flags.uv,
        attestation_object=attestation_object_bytes,
        credential_device_type=parsed_backup_flags.credential_device_type,
        credential_backed_up=parsed_backup_flags.credential_backed_up,
    )
