import hmac
import struct
import time

TOTP_SECRET_SIZE = 160

ALGORITHM = "sha1"
DIGITS = 6
TIMESTEP = 30


class TOTP:
    def __init__(self, key) -> None:
        self._key = key

    def match(self, code, t=None, window=TIMESTEP, timestep=TIMESTEP):
        if t is None:
            t = time.time()

        low = int((t - window) / timestep)
        high = int((t + window) / timestep) + 1

        return next(
            (
                counter
                for counter in range(low, high)
                if hotp(self._key, counter) == code
            ),
            None,
        )


def hotp(secret, counter):
    C = struct.pack(">Q", counter)
    mac = hmac.new(secret, msg=C, digestmod=ALGORITHM).digest()
    offset = mac[-1] & 0xF
    code = struct.unpack_from(">I", mac, offset)[0] & 0x7FFFFFFF
    return code % (10**DIGITS)
