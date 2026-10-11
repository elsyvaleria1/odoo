from typing import List, Optional

from ..helpers import generate_challenge
from ..helpers.structs import (
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRequestOptions,
    UserVerificationRequirement,
)


def generate_authentication_options(
    *,
    rp_id: str,
    challenge: Optional[bytes] = None,
    timeout: int = 60000,
    allow_credentials: Optional[List[PublicKeyCredentialDescriptor]] = None,
    user_verification: UserVerificationRequirement = UserVerificationRequirement.PREFERRED,
) -> PublicKeyCredentialRequestOptions:

    if not rp_id:
        raise ValueError("rp_id cannot be an empty string")


    if not challenge:
        challenge = generate_challenge()

    if not allow_credentials:
        allow_credentials = []

    return PublicKeyCredentialRequestOptions(
        rp_id=rp_id,
        challenge=challenge,
        timeout=timeout,
        allow_credentials=allow_credentials,
        user_verification=user_verification,
    )
