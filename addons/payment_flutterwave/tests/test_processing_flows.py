from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_flutterwave.controllers.main import FlutterwaveController
from odoo.addons.payment_flutterwave.tests.common import FlutterwaveCommon


@tagged("post_install", "-at_install")
class TestProcessingFlows(FlutterwaveCommon, PaymentHttpCommon):
    @mute_logger("odoo.addons.payment_flutterwave.models.payment_transaction")
    def test_redirect_notification_triggers_processing(self):
        """Test that receiving a redirect notification triggers the processing of the notification
        data."""
        self._create_transaction(flow="redirect")
        url = self._build_url(FlutterwaveController._return_url)
        with (
            patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
                return_value=self.verification_data,
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_http_get_request(url, params=self.redirect_payment_data)
        self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_flutterwave.models.payment_transaction")
    def test_webhook_notification_triggers_processing(self):
        """Test that receiving a valid webhook notification triggers the processing of the
        payment data."""
        self._create_transaction("redirect")
        url = self._build_url(FlutterwaveController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_flutterwave.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_json_request(url, data=self.webhook_payment_data)
        self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_flutterwave.models.payment_transaction")
    def test_webhook_notification_triggers_signature_check(self):
        """Test that receiving a webhook notification triggers a signature check."""
        self._create_transaction("redirect")
        url = self._build_url(FlutterwaveController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_flutterwave.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_json_request(url, data=self.webhook_payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_webhook_notification_with_valid_signature(self):
        """Test the verification of a webhook notification with a valid signature."""
        tx = self._create_transaction("redirect")
        self.assertTrue(
            tx._is_flutterwave_signature_valid(self.provider.flutterwave_webhook_secret)
        )

    @mute_logger("odoo.addons.payment_flutterwave.models.payment_transaction")
    def test_reject_notification_with_missing_signature(self):
        """Test the verification of a notification with a missing signature."""
        tx = self._create_transaction("redirect")
        self.assertFalse(tx._is_flutterwave_signature_valid(None))

    @mute_logger("odoo.addons.payment_flutterwave.models.payment_transaction")
    def test_reject_notification_with_invalid_signature(self):
        """Test the verification of a notification with an invalid signature."""
        tx = self._create_transaction("redirect")
        self.assertFalse(tx._is_flutterwave_signature_valid("dummy"))

    @mute_logger("odoo.addons.payment_flutterwave.models.payment_transaction")
    def test_reject_notification_with_a_non_ascii_signature(self):
        """Test that a non-ASCII signature is refused, not raised on."""
        tx = self._create_transaction("redirect")
        self.assertFalse(tx._is_flutterwave_signature_valid("é" * 32))

    @mute_logger("odoo.addons.payment_flutterwave.controllers.main")
    def test_a_malformed_webhook_body_is_refused_without_a_traceback(self):
        url = self._build_url(FlutterwaveController._webhook_url)
        for body in ("not json", [], {"event": "charge.completed", "data": ["tx"]}):
            with self.subTest(body=body):
                self.assertEqual(self._post_malformed_json(url, body).status_code, 400)

    @mute_logger(
        "odoo.addons.payment_flutterwave.controllers.main",
        "odoo.addons.payment.models.payment_transaction",
    )
    def test_an_authorization_response_that_is_no_json_object_returns_to_the_status_page(
        self,
    ):
        url = self._build_url(FlutterwaveController._auth_return_url)
        for response in ("not json", "[]"):
            with self.subTest(response=response):
                with self._assertNoTracebackLogged():
                    reply = self.url_open(
                        url, params={"response": response}, allow_redirects=False
                    )
                self.assertEqual(reply.status_code, 303)
                self.assertTrue(reply.headers["Location"].endswith("/payment/status"))
