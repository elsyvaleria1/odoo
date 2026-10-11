from ..exceptions import InvalidTPMCertInfoStructure
from .structs import (
    TPM_ST,
    TPM_ST_MAP,
    TPMCertInfo,
    TPMCertInfoAttested,
    TPMCertInfoClockInfo,
)


def parse_cert_info(val: bytes) -> TPMCertInfo:
    pointer = 0

    magic_bytes = val[pointer : pointer + 4]
    pointer += 4

    type_bytes = val[pointer : pointer + 2]
    pointer += 2
    mapped_type = TPM_ST_MAP[type_bytes]

    qualified_signer_length = int.from_bytes(val[pointer : pointer + 2], "big")
    pointer += 2
    qualified_signer = val[pointer : pointer + qualified_signer_length]
    pointer += qualified_signer_length

    extra_data_length = int.from_bytes(val[pointer : pointer + 2], "big")
    pointer += 2
    extra_data_bytes = val[pointer : pointer + extra_data_length]
    pointer += extra_data_length

    clock_info_bytes = val[pointer : pointer + 17]
    pointer += 17

    firmware_version_bytes = val[pointer : pointer + 8]
    pointer += 8

    if mapped_type != TPM_ST.ATTEST_CERTIFY:
        raise InvalidTPMCertInfoStructure(
            f'Cert Info type "{mapped_type}" was not "{TPM_ST.ATTEST_CERTIFY}"'
        )

    attested_name_length = int.from_bytes(val[pointer : pointer + 2], "big")
    pointer += 2
    attested_name_bytes = val[pointer : pointer + attested_name_length]
    pointer += attested_name_length
    qualified_name_length = int.from_bytes(val[pointer : pointer + 2], "big")
    pointer += 2
    qualified_name_bytes = val[pointer : pointer + qualified_name_length]
    pointer += qualified_name_length

    return TPMCertInfo(
        magic=magic_bytes,
        type=mapped_type,
        extra_data=extra_data_bytes,
        attested=TPMCertInfoAttested(attested_name_bytes, qualified_name_bytes),
        qualified_signer=qualified_signer,
        clock_info=TPMCertInfoClockInfo(clock_info_bytes),
        firmware_version=firmware_version_bytes,
    )
