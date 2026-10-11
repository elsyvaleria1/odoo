import base64
import hashlib
import hmac
from unittest.mock import patch

import requests

from odoo.exceptions import ValidationError
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.payment_iyzico.tests.common import IyzicoCommon


@tagged("post_install", "-at_install")
class TestPaymentProvider(IyzicoCommon):
    def test_signature_calculation_for_outgoing_data(self):
        calculated_signature = self.provider._get_iyzico_signature(
            "/dummy", b'{"dummy": "dummy"}', "random_string"
        )
        expected_signature = (
            "ad5a61b79b941a805bb95aecac0ae2c9c4889fd92f534830be87c6b8d5d8fc2f"
        )
        self.assertEqual(calculated_signature, expected_signature)

    def test_the_signature_is_over_the_body_that_is_sent(self):
        sent = {}

        def capture(connection, method, url, **kwargs):
            sent.update(kwargs)
            raise requests.exceptions.ConnectionError

        payload = {"locale": "tr", "conversationId": "S00001", "price": "1.0"}
        endpoint = "payment/iyzipos/checkoutform/auth/ecom/detail"
        with (
            patch.object(
                type(self.env["integration.connection"]), "_egress_request", capture
            ),
            self.assertRaises(ValidationError),
        ):
            self.provider._send_api_request("POST", endpoint, json=payload)

        self.assertEqual(json_loads(sent["data"]), payload)
        self.assertNotIn("json", sent)
        self.assertEqual(sent["headers"]["Content-Type"], "application/json")
        authorization = dict(
            part.split(":", 1)
            for part in base64.b64decode(
                sent["headers"]["Authorization"].removeprefix("IYZWSv2 ")
            )
            .decode()
            .split("&")
        )
        self.assertEqual(sent["headers"]["x-iyzi-rnd"], authorization["randomKey"])
        message = f"{authorization['randomKey']}/{endpoint}{sent['data'].decode()}"
        self.assertEqual(
            authorization["signature"],
            hmac.new(b"iyzipay_secret", message.encode(), hashlib.sha256).hexdigest(),
        )
