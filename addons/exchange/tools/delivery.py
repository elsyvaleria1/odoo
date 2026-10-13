from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from odoo.addons.integration.tools import CommError

if TYPE_CHECKING:
    from collections.abc import Iterator


class NotDelivered(Exception):
    pass


class DeliveryUnknown(Exception):
    pass


def is_delivery_refused(error: CommError) -> bool:
    return not error.is_delivered or 400 <= (error.status_code or 0) < 500


@contextmanager
def typed_delivery() -> Iterator[None]:
    try:
        yield
    except CommError as error:
        if is_delivery_refused(error):
            raise NotDelivered(error.message) from error
        raise DeliveryUnknown(error.message) from error
