import time

import freezegun

freezegun.configure(extend_ignore_list=[__name__])


def monotonic() -> float:
    return time.monotonic()


def wall() -> float:
    return time.time()
