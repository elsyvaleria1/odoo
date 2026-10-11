from enum import Enum
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Union

from .cose import COSEAlgorithmIdentifier




class AuthenticatorTransport(str, Enum):

    USB = "usb"
    NFC = "nfc"
    BLE = "ble"
    INTERNAL = "internal"
    CABLE = "cable"
    HYBRID = "hybrid"


class AuthenticatorAttachment(str, Enum):

    PLATFORM = "platform"
    CROSS_PLATFORM = "cross-platform"


class ResidentKeyRequirement(str, Enum):

    DISCOURAGED = "discouraged"
    PREFERRED = "preferred"
    REQUIRED = "required"


class UserVerificationRequirement(str, Enum):

    REQUIRED = "required"
    PREFERRED = "preferred"
    DISCOURAGED = "discouraged"


class AttestationConveyancePreference(str, Enum):

    NONE = "none"
    INDIRECT = "indirect"
    DIRECT = "direct"
    ENTERPRISE = "enterprise"


class PublicKeyCredentialType(str, Enum):

    PUBLIC_KEY = "public-key"


class AttestationFormat(str, Enum):

    PACKED = "packed"
    TPM = "tpm"
    ANDROID_KEY = "android-key"
    ANDROID_SAFETYNET = "android-safetynet"
    FIDO_U2F = "fido-u2f"
    APPLE = "apple"
    NONE = "none"


class ClientDataType(str, Enum):

    WEBAUTHN_CREATE = "webauthn.create"
    WEBAUTHN_GET = "webauthn.get"


class TokenBindingStatus(str, Enum):

    PRESENT = "present"
    SUPPORTED = "supported"


@dataclass
class TokenBinding:

    status: TokenBindingStatus
    id: Optional[str] = None


@dataclass
class PublicKeyCredentialRpEntity:

    name: str
    id: Optional[str] = None


@dataclass
class PublicKeyCredentialUserEntity:

    id: bytes
    name: str
    display_name: str


@dataclass
class PublicKeyCredentialParameters:

    type: Literal["public-key"]
    alg: COSEAlgorithmIdentifier


@dataclass
class PublicKeyCredentialDescriptor:

    id: bytes
    type: Literal[PublicKeyCredentialType.PUBLIC_KEY] = PublicKeyCredentialType.PUBLIC_KEY
    transports: Optional[List[AuthenticatorTransport]] = None


@dataclass
class AuthenticatorSelectionCriteria:

    authenticator_attachment: Optional[AuthenticatorAttachment] = None
    resident_key: Optional[ResidentKeyRequirement] = None
    require_resident_key: Optional[bool] = False
    user_verification: Optional[
        UserVerificationRequirement
    ] = UserVerificationRequirement.PREFERRED


@dataclass
class CollectedClientData:

    type: ClientDataType
    challenge: bytes
    origin: str
    cross_origin: Optional[bool] = None
    token_binding: Optional[TokenBinding] = None




@dataclass
class PublicKeyCredentialCreationOptions:

    rp: PublicKeyCredentialRpEntity
    user: PublicKeyCredentialUserEntity
    challenge: bytes
    pub_key_cred_params: List[PublicKeyCredentialParameters]
    timeout: Optional[int] = None
    exclude_credentials: Optional[List[PublicKeyCredentialDescriptor]] = None
    authenticator_selection: Optional[AuthenticatorSelectionCriteria] = None
    attestation: AttestationConveyancePreference = AttestationConveyancePreference.NONE


@dataclass
class AuthenticatorAttestationResponse:

    client_data_json: bytes
    attestation_object: bytes
    transports: Optional[List[AuthenticatorTransport]] = None


@dataclass
class RegistrationCredential:

    id: str
    raw_id: bytes
    response: AuthenticatorAttestationResponse
    authenticator_attachment: Optional[AuthenticatorAttachment] = None
    type: Literal[PublicKeyCredentialType.PUBLIC_KEY] = PublicKeyCredentialType.PUBLIC_KEY


@dataclass
class AttestationStatement:

    sig: Optional[bytes] = None
    x5c: Optional[List[bytes]] = None
    response: Optional[bytes] = None
    alg: Optional[COSEAlgorithmIdentifier] = None
    ver: Optional[str] = None
    cert_info: Optional[bytes] = None
    pub_area: Optional[bytes] = None


@dataclass
class AuthenticatorDataFlags:

    up: bool
    uv: bool
    be: bool
    bs: bool
    at: bool
    ed: bool


@dataclass
class AttestedCredentialData:

    aaguid: bytes
    credential_id: bytes
    credential_public_key: bytes


@dataclass
class AuthenticatorData:

    rp_id_hash: bytes
    flags: AuthenticatorDataFlags
    sign_count: int
    attested_credential_data: Optional[AttestedCredentialData] = None
    extensions: Optional[bytes] = None


@dataclass
class AttestationObject:

    fmt: AttestationFormat
    auth_data: AuthenticatorData
    att_stmt: AttestationStatement = field(default_factory=AttestationStatement)




@dataclass
class PublicKeyCredentialRequestOptions:

    challenge: bytes
    timeout: Optional[int] = None
    rp_id: Optional[str] = None
    allow_credentials: Optional[List[PublicKeyCredentialDescriptor]] = None
    user_verification: Optional[
        UserVerificationRequirement
    ] = UserVerificationRequirement.PREFERRED


@dataclass
class AuthenticatorAssertionResponse:

    client_data_json: bytes
    authenticator_data: bytes
    signature: bytes
    user_handle: Optional[bytes] = None


@dataclass
class AuthenticationCredential:

    id: str
    raw_id: bytes
    response: AuthenticatorAssertionResponse
    authenticator_attachment: Optional[AuthenticatorAttachment] = None
    type: Literal[PublicKeyCredentialType.PUBLIC_KEY] = PublicKeyCredentialType.PUBLIC_KEY




class CredentialDeviceType(str, Enum):

    SINGLE_DEVICE = "single_device"
    MULTI_DEVICE = "multi_device"
