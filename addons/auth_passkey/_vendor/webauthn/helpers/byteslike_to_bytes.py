from typing import Union


def byteslike_to_bytes(val: Union[bytes, memoryview]) -> bytes:
    if isinstance(val, memoryview):
        val = val.tobytes()

    return bytes(val)
