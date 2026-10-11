from enum import Enum


class COSEAlgorithmIdentifier(int, Enum):

    ECDSA_SHA_256 = -7
    EDDSA = -8
    ECDSA_SHA_512 = -36
    RSASSA_PSS_SHA_256 = -37
    RSASSA_PSS_SHA_384 = -38
    RSASSA_PSS_SHA_512 = -39
    RSASSA_PKCS1_v1_5_SHA_256 = -257
    RSASSA_PKCS1_v1_5_SHA_384 = -258
    RSASSA_PKCS1_v1_5_SHA_512 = -259
    RSASSA_PKCS1_v1_5_SHA_1 = -65535


class COSEKTY(int, Enum):

    OKP = 1
    EC2 = 2
    RSA = 3


class COSECRV(int, Enum):

    P256 = 1
    P384 = 2
    P521 = 3
    ED25519 = 6


class COSEKey(int, Enum):

    KTY = 1
    ALG = 3
    CRV = -1
    X = -2
    Y = -3
    N = -1
    E = -2
