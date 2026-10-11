import codecs


def aaguid_to_string(val: bytes) -> str:
    if len(val) != 16:
        raise ValueError(f"AAGUID was {len(val)} bytes, expected 16 bytes")

    to_hex = codecs.encode(val, encoding="hex").decode("utf-8")

    seg_1 = to_hex[0:8]
    seg_2 = to_hex[8:12]
    seg_3 = to_hex[12:16]
    seg_4 = to_hex[16:20]
    seg_5 = to_hex[20:32]

    return f"{seg_1}-{seg_2}-{seg_3}-{seg_4}-{seg_5}"
