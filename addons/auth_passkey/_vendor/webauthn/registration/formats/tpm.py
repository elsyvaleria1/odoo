from typing import List

import cbor2
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.x509 import (
    ExtendedKeyUsage,
    GeneralName,
    Name,
    SubjectAlternativeName,
    Version,
    BasicConstraints,
)
from cryptography.x509.extensions import ExtensionNotFound
from cryptography.x509.oid import ExtensionOID

from ....webauthn.helpers import (
    decode_credential_public_key,
    hash_by_alg,
    parse_cbor,
    validate_certificate_chain,
    verify_signature,
)
from ....webauthn.helpers.decode_credential_public_key import (
    DecodedEC2PublicKey,
    DecodedRSAPublicKey,
)
from ....webauthn.helpers.exceptions import (
    InvalidCertificateChain,
    InvalidRegistrationResponse,
)
from ....webauthn.helpers.structs import AttestationStatement
from ....webauthn.helpers.tpm import parse_cert_info, parse_pub_area
from ....webauthn.helpers.tpm.structs import (
    TPM_ALG_COSE_ALG_MAP,
    TPM_ECC_CURVE_COSE_CRV_MAP,
    TPM_MANUFACTURERS,
    TPMPubAreaParametersECC,
    TPMPubAreaParametersRSA,
)


def verify_tpm(
    *,
    attestation_statement: AttestationStatement,
    attestation_object: bytes,
    client_data_json: bytes,
    credential_public_key: bytes,
    pem_root_certs_bytes: List[bytes],
) -> bool:
    if not attestation_statement.cert_info:
        raise InvalidRegistrationResponse("Attestation statement was missing certInfo (TPM)")

    if not attestation_statement.pub_area:
        raise InvalidRegistrationResponse("Attestation statement was missing pubArea (TPM)")

    if not attestation_statement.alg:
        raise InvalidRegistrationResponse("Attestation statement was missing alg (TPM)")

    if not attestation_statement.x5c:
        raise InvalidRegistrationResponse("Attestation statement was missing x5c (TPM)")

    if not attestation_statement.sig:
        raise InvalidRegistrationResponse("Attestation statement was missing sig (TPM)")

    att_stmt_ver = attestation_statement.ver
    if att_stmt_ver != "2.0":
        raise InvalidRegistrationResponse(
            f'Attestation statement ver "{att_stmt_ver}" was not "2.0" (TPM)'
        )

    try:
        validate_certificate_chain(
            x5c=attestation_statement.x5c,
            pem_root_certs_bytes=pem_root_certs_bytes,
        )
    except InvalidCertificateChain as err:
        raise InvalidRegistrationResponse(f"{err} (TPM)")

    pub_area = parse_pub_area(attestation_statement.pub_area)
    decoded_public_key = decode_credential_public_key(credential_public_key)

    if isinstance(pub_area.parameters, TPMPubAreaParametersRSA):
        if not isinstance(decoded_public_key, DecodedRSAPublicKey):
            raise InvalidRegistrationResponse(
                "Public key was not RSA key as indicated in pubArea (TPM)"
            )

        if pub_area.unique.value != decoded_public_key.n:
            unique_hex = pub_area.unique.value.hex()
            pub_key_n_hex = decoded_public_key.n.hex()
            raise InvalidRegistrationResponse(
                f'PubArea unique "{unique_hex}" was not same as public key modulus "{pub_key_n_hex}" (TPM)'
            )

        pub_area_exponent = int.from_bytes(pub_area.parameters.exponent, "big")
        if pub_area_exponent == 0:
            pub_area_exponent = 65537

        pub_key_exponent = int.from_bytes(decoded_public_key.e, "big")

        if pub_area_exponent != pub_key_exponent:
            raise InvalidRegistrationResponse(
                f'PubArea exponent "{pub_area_exponent}" was not same as public key exponent "{pub_key_exponent}" (TPM)'
            )
    elif isinstance(pub_area.parameters, TPMPubAreaParametersECC):
        if not isinstance(decoded_public_key, DecodedEC2PublicKey):
            raise InvalidRegistrationResponse(
                "Public key was not ECC key as indicated in pubArea (TPM)"
            )

        pubKeyCoords = b"".join([decoded_public_key.x, decoded_public_key.y])
        if pub_area.unique.value != pubKeyCoords:
            unique_hex = pub_area.unique.value.hex()
            pub_key_xy_hex = pubKeyCoords.hex()
            raise InvalidRegistrationResponse(
                f'Unique "{unique_hex}" was not same as public key [x,y] "{pub_key_xy_hex}" (TPM)'
            )

        pub_area_crv = TPM_ECC_CURVE_COSE_CRV_MAP[pub_area.parameters.curve_id]
        if pub_area_crv != decoded_public_key.crv:
            raise InvalidRegistrationResponse(
                f'PubArea curve ID "{pub_area_crv}" was not same as public key crv "{decoded_public_key.crv}" (TPM)'
            )
    else:
        pub_area_param_type = type(pub_area.parameters)
        raise InvalidRegistrationResponse(
            f'Unsupported pub_area.parameters "{pub_area_param_type}" (TPM)'
        )

    cert_info = parse_cert_info(attestation_statement.cert_info)

    magic_int = int.from_bytes(cert_info.magic, "big")
    if magic_int != int(0xFF544347):
        raise InvalidRegistrationResponse(
            f'CertInfo magic "{magic_int}" was not TPM_GENERATED_VALUE 4283712327 (0xff544347) (TPM)'
        )

    attestation_dict = parse_cbor(attestation_object)
    authenticator_data_bytes: bytes = attestation_dict["authData"]
    client_data_hash = hash_by_alg(client_data_json)
    att_to_be_signed = b"".join(
        [
            authenticator_data_bytes,
            client_data_hash,
        ]
    )

    att_to_be_signed_hash = hash_by_alg(att_to_be_signed, attestation_statement.alg)
    if cert_info.extra_data != att_to_be_signed_hash:
        raise InvalidRegistrationResponse(
            "PubArea extra data did not match hash of auth data and client data (TPM)"
        )

    pub_area_hash = hash_by_alg(
        attestation_statement.pub_area,
        TPM_ALG_COSE_ALG_MAP[pub_area.name_alg],
    )

    attested_name = b"".join(
        [
            cert_info.attested.name_alg_bytes,
            pub_area_hash,
        ]
    )

    if attested_name != cert_info.attested.name:
        raise InvalidRegistrationResponse(
            "CertInfo attested name did not match PubArea hash (TPM)"
        )

    attestation_cert_bytes = attestation_statement.x5c[0]
    attestation_cert = x509.load_der_x509_certificate(attestation_cert_bytes)
    attestation_cert_pub_key = attestation_cert.public_key()

    try:
        verify_signature(
            public_key=attestation_cert_pub_key,
            signature_alg=attestation_statement.alg,
            signature=attestation_statement.sig,
            data=attestation_statement.cert_info,
        )
    except InvalidSignature:
        raise InvalidRegistrationResponse("Could not verify attestation statement signature (TPM)")


    if attestation_cert.version != Version.v3:
        raise InvalidRegistrationResponse(
            f'Certificate Version "{attestation_cert.version}" was not "{Version.v3}"" Constraints CA was not False (TPM)'
        )

    if len(attestation_cert.subject) > 0:
        raise InvalidRegistrationResponse(
            f'Certificate Subject "{attestation_cert.subject}" was not empty (TPM)'
        )

    cert_extensions = attestation_cert.extensions

    try:
        ext_subject_alt_name: SubjectAlternativeName = cert_extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        ).value
    except ExtensionNotFound:
        raise InvalidRegistrationResponse(
            f"Certificate missing extension {ExtensionOID.SUBJECT_ALTERNATIVE_NAME} (TPM)"
        )

    tcg_at_tpm_values: Name = ext_subject_alt_name.get_values_for_type(GeneralName)[0]
    tcg_at_tpm_manufacturer = None
    tcg_at_tpm_model = None
    tcg_at_tpm_version = None
    for obj in tcg_at_tpm_values:
        oid = obj.oid.dotted_string
        if oid == "2.23.133.2.1":
            tcg_at_tpm_manufacturer = str(obj.value)
        elif oid == "2.23.133.2.2":
            tcg_at_tpm_model = obj.value
        elif oid == "2.23.133.2.3":
            tcg_at_tpm_version = obj.value

    if not tcg_at_tpm_manufacturer or not tcg_at_tpm_model or not tcg_at_tpm_version:
        raise InvalidRegistrationResponse(
            f"Certificate Subject Alt Name was invalid value {tcg_at_tpm_values} (TPM)",
        )

    try:
        TPM_MANUFACTURERS[tcg_at_tpm_manufacturer]
    except KeyError:
        raise InvalidRegistrationResponse(
            f'Unrecognized TPM Manufacturer "{tcg_at_tpm_manufacturer}" (TPM)'
        )

    try:
        ext_extended_key_usage: ExtendedKeyUsage = cert_extensions.get_extension_for_oid(
            ExtensionOID.EXTENDED_KEY_USAGE
        ).value
    except ExtensionNotFound:
        raise InvalidRegistrationResponse(
            f"Certificate missing extension {ExtensionOID.EXTENDED_KEY_USAGE} (TPM)"
        )

    ext_key_usage_oid = ext_extended_key_usage[0].dotted_string

    if ext_key_usage_oid != "2.23.133.8.3":
        raise InvalidRegistrationResponse(
            f'Certificate Extended Key Usage OID "{ext_key_usage_oid}" was not "2.23.133.8.3" (TPM)'
        )

    try:
        ext_basic_constraints: BasicConstraints = cert_extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS
        ).value
    except ExtensionNotFound:
        raise InvalidRegistrationResponse(
            f"Certificate missing extension {ExtensionOID.BASIC_CONSTRAINTS} (TPM)"
        )

    if ext_basic_constraints.ca is not False:
        raise InvalidRegistrationResponse("Certificate Basic Constraints CA was not False (TPM)")


    return True
