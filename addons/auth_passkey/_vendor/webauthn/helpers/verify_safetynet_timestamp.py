import time


def verify_safetynet_timestamp(timestamp_ms: int) -> None:
    grace_ms = 10 * 1000
    now = int(time.time()) * 1000

    if timestamp_ms > (now + grace_ms):
        raise ValueError(f"Payload timestamp {timestamp_ms} was later than {now} + {grace_ms}")

    if timestamp_ms < (now - grace_ms):
        raise ValueError("Payload has expired")
