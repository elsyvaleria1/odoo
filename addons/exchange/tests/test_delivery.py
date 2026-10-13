from odoo.tests.common import BaseCase

from odoo.addons.exchange.tools import DeliveryUnknown, NotDelivered, typed_delivery
from odoo.addons.integration.tools import (
    AuthenticationError,
    CircuitOpenError,
    ClientError,
    CommError,
    CommTimeoutError,
    HostNotAllowedError,
    RateLimitError,
    ServerError,
)


class TestTypedDelivery(BaseCase):
    def _typed(self, error):
        with self.assertRaises((NotDelivered, DeliveryUnknown)) as caught:
            with typed_delivery():
                raise error
        self.assertIs(caught.exception.__cause__, error)
        return type(caught.exception)

    def test_a_request_that_never_left_is_not_delivered(self):
        for error in (
            CommError("name or service not known", is_delivered=False),
            CommTimeoutError("connect timed out", is_delivered=False),
            RateLimitError("call budget spent", is_delivered=False),
            CircuitOpenError(),
            HostNotAllowedError(),
        ):
            with self.subTest(error=error):
                self.assertIs(self._typed(error), NotDelivered)

    def test_a_request_the_counterparty_refused_is_not_delivered(self):
        for error in (
            ClientError("bad request", 400),
            AuthenticationError("unauthorized", 401),
            RateLimitError("too many requests", 429),
        ):
            with self.subTest(error=error):
                self.assertIs(self._typed(error), NotDelivered)

    def test_a_request_that_may_have_arrived_has_an_unknown_outcome(self):
        for error in (
            CommTimeoutError("read timed out"),
            CommError("connection aborted"),
            ServerError("bad gateway", 502),
            ServerError("retries exhausted"),
        ):
            with self.subTest(error=error):
                self.assertIs(self._typed(error), DeliveryUnknown)

    def test_what_is_not_a_transport_error_is_left_to_its_caller(self):
        with self.assertRaises(KeyError), typed_delivery():
            raise KeyError("body")
