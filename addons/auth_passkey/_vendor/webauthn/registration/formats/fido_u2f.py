import hashlib
from typing import List

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePublicKey,
)

from ....webauthn.helpers import (
    aaguid_to_string,
    validate_certificate_chain,
    verify_signature,
)
from ....webauthn.helpers.cose import COSEAlgorithmIdentifier
from ....webauthn.helpers.decode_credential_public_key import (
    DecodedEC2PublicKey,
    decode_credential_public_key,
)
from ....webauthn.helpers.exceptions import (
    InvalidCertificateChain,
    InvalidRegistrationResponse,
)
from ....webauthn.helpers.structs import AttestationStatement


def verify_fido_u2f(
    *,
    attestation_statement: AttestationStatement,
    client_data_json: bytes,
    rp_id_hash: bytes,
    credential_id: bytes,
    credential_public_key: bytes,
    aaguid: bytes,
    pem_root_certs_bytes: List[bytes],
) -> bool:
    if not attestation_statement.sig:
        raise InvalidRegistrationResponse("Attestation statement was missing signature (FIDO-U2F)")

    if not attestation_statement.x5c:
        raise InvalidRegistrationResponse(
            "Attestation statement was missing certificate (FIDO-U2F)"
        )

    if len(attestation_statement.x5c) > 1:
        raise InvalidRegistrationResponse(
            "Attestation statement contained too many certificates (FIDO-U2F)"
        )

    try:
        validate_certificate_chain(
            x5c=attestation_statement.x5c,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    except InvalidCertificateChain as err:
        raise InvalidRegistrationResponse(f"{err} (FIDO-U2F)")

    actual_aaguid = aaguid_to_string(aaguid)
    expected_aaguid = "00000000-0000-0000-0000-000000000000"
    if actual_aaguid != expected_aaguid:
        raise InvalidRegistrationResponse(
            f"AAGUID {actual_aaguid} was not expected {expected_aaguid} (FIDO-U2F)"
        )

    leaf_cert_bytes = attestation_statement.x5c[0]
    leaf_cert = x509.load_der_x509_certificate(leaf_cert_bytes)
    leaf_cert_pub_key = leaf_cert.public_key()

    if not isinstance(leaf_cert_pub_key, EllipticCurvePublicKey):
        raise InvalidRegistrationResponse("Leaf cert was not an EC2 certificate (FIDO-U2F)")

    if not isinstance(leaf_cert_pub_key.curve, SECP256R1):
        raise InvalidRegistrationResponse("Leaf cert did not use P-256 curve (FIDO-U2F)")

    decoded_public_key = decode_credential_public_key(credential_public_key)
    if not isinstance(decoded_public_key, DecodedEC2PublicKey):
        raise InvalidRegistrationResponse("Credential public key was not EC2 (FIDO-U2F)")

    public_key_u2f = b"".join(
        [
            bytes([0x04]),
            decoded_public_key.x,
            decoded_public_key.y,
        ]
    )

    client_data_hash = hashlib.sha256()
    client_data_hash.update(client_data_json)
    client_data_hash_bytes = client_data_hash.digest()

    verification_data = b"".join(
        [
            bytes([0x00]),
            rp_id_hash,
            client_data_hash_bytes,
            credential_id,
            public_key_u2f,
        ]
    )

    try:
        verify_signature(
            public_key=leaf_cert_pub_key,
            signature_alg=COSEAlgorithmIdentifier.ECDSA_SHA_256,
            signature=attestation_statement.sig,
            data=verification_data,
        )
    except InvalidSignature:
        raise InvalidRegistrationResponse(
            "Could not verify attestation statement signature (FIDO-U2F)"
        )

    return True
