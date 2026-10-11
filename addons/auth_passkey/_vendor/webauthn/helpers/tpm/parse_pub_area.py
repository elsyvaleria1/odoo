from ..exceptions import InvalidTPMPubAreaStructure
from .structs import (
    TPM_ALG,
    TPM_ALG_MAP,
    TPMPubArea,
    TPMPubAreaObjectAttributes,
    TPMPubAreaParametersECC,
    TPMPubAreaParametersRSA,
    TPMPubAreaUnique,
)


def parse_pub_area(val: bytes) -> TPMPubArea:
    pointer = 0

    type_bytes = val[pointer : pointer + 2]
    pointer += 2
    mapped_type = TPM_ALG_MAP[type_bytes]

    name_alg_bytes = val[pointer : pointer + 2]
    pointer += 2
    mapped_name_alg = TPM_ALG_MAP[name_alg_bytes]

    object_attributes_bytes = val[pointer : pointer + 4]
    pointer += 4
    object_attributes = TPMPubAreaObjectAttributes(object_attributes_bytes)

    auth_policy_length = int.from_bytes(val[pointer : pointer + 2], "big")
    pointer += 2
    auth_policy_bytes = val[pointer : pointer + auth_policy_length]
    pointer += auth_policy_length

    if mapped_type == TPM_ALG.RSA:
        rsa_bytes = val[pointer : pointer + 10]
        pointer += 10
        parameters = TPMPubAreaParametersRSA(rsa_bytes)
    elif mapped_type == TPM_ALG.ECC:
        ecc_bytes = val[pointer : pointer + 8]
        pointer += 8
        parameters = TPMPubAreaParametersECC(ecc_bytes)
    else:
        raise InvalidTPMPubAreaStructure(f'Type "{mapped_type}" is unsupported')

    unique_length_bytes = val[pointer:]

    return TPMPubArea(
        type=mapped_type,
        name_alg=mapped_name_alg,
        object_attributes=object_attributes,
        auth_policy=auth_policy_bytes,
        parameters=parameters,
        unique=TPMPubAreaUnique(unique_length_bytes, mapped_type),
    )
