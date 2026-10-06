import time

import freezegun

# A test freezes the product's clock, never the harness's: freezegun answers a
# read made from an ignored module with the real clock.
freezegun.configure(extend_ignore_list=[__name__])


def monotonic() -> float:
    return time.monotonic()


def wall() -> float:
    return time.time()
