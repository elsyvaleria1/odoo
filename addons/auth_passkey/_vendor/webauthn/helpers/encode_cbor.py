from typing import Any

import cbor2

from .exceptions import InvalidCBORData


def encode_cbor(val: Any) -> bytes:
    try:
        to_return = cbor2.dumps(val)
    except Exception as exc:
        raise InvalidCBORData("Data could not be encoded to CBOR") from exc

    return to_return
