from typing import List, Optional

from ...webauthn.helpers import generate_challenge, generate_user_handle, byteslike_to_bytes
from ...webauthn.helpers.cose import COSEAlgorithmIdentifier
from ...webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialCreationOptions,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialParameters,
    PublicKeyCredentialRpEntity,
    PublicKeyCredentialUserEntity,
    ResidentKeyRequirement,
)


def _generate_pub_key_cred_params(
    supported_algs: List[COSEAlgorithmIdentifier],
) -> List[PublicKeyCredentialParameters]:
    return [PublicKeyCredentialParameters(type="public-key", alg=alg) for alg in supported_algs]


default_supported_pub_key_algs = [
    COSEAlgorithmIdentifier.ECDSA_SHA_256,
    COSEAlgorithmIdentifier.EDDSA,
    COSEAlgorithmIdentifier.ECDSA_SHA_512,
    COSEAlgorithmIdentifier.RSASSA_PSS_SHA_256,
    COSEAlgorithmIdentifier.RSASSA_PSS_SHA_384,
    COSEAlgorithmIdentifier.RSASSA_PSS_SHA_512,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_384,
    COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_512,
]
default_supported_pub_key_params = _generate_pub_key_cred_params(
    default_supported_pub_key_algs,
)


def generate_registration_options(
    *,
    rp_id: str,
    rp_name: str,
    user_name: str,
    user_id: Optional[bytes] = None,
    user_display_name: Optional[str] = None,
    challenge: Optional[bytes] = None,
    timeout: int = 60000,
    attestation: AttestationConveyancePreference = AttestationConveyancePreference.NONE,
    authenticator_selection: Optional[AuthenticatorSelectionCriteria] = None,
    exclude_credentials: Optional[List[PublicKeyCredentialDescriptor]] = None,
    supported_pub_key_algs: Optional[List[COSEAlgorithmIdentifier]] = None,
) -> PublicKeyCredentialCreationOptions:

    if not rp_id:
        raise ValueError("rp_id cannot be an empty string")

    if not rp_name:
        raise ValueError("rp_name cannot be an empty string")

    if not user_name:
        raise ValueError("user_name cannot be an empty string")

    if user_id:
        if not isinstance(user_id, bytes):
            raise ValueError("user_id must be bytes")
    else:
        user_id = generate_user_handle()


    if not user_display_name:
        user_display_name = user_name

    pub_key_cred_params = default_supported_pub_key_params
    if supported_pub_key_algs:
        pub_key_cred_params = _generate_pub_key_cred_params(supported_pub_key_algs)

    if not challenge:
        challenge = generate_challenge()

    if not exclude_credentials:
        exclude_credentials = []


    options = PublicKeyCredentialCreationOptions(
        rp=PublicKeyCredentialRpEntity(
            name=rp_name,
            id=rp_id,
        ),
        user=PublicKeyCredentialUserEntity(
            id=user_id,
            name=user_name,
            display_name=user_display_name,
        ),
        challenge=challenge,
        pub_key_cred_params=pub_key_cred_params,
        timeout=timeout,
        exclude_credentials=exclude_credentials,
        attestation=attestation,
    )


    if authenticator_selection is not None:
        if authenticator_selection.resident_key == ResidentKeyRequirement.REQUIRED:
            authenticator_selection.require_resident_key = True
        options.authenticator_selection = authenticator_selection

    return options
