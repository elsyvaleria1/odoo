import hashlib
import hmac
from base64 import b64encode
from unittest.mock import patch

from requests import Response

from odoo.libs.guarded_http import GuardedSession
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_worldline.controllers.main import WorldlineController
from odoo.addons.payment_worldline.tests.common import WorldlineCommon


@tagged("post_install", "-at_install")
class WorldlineTest(WorldlineCommon, PaymentHttpCommon):
    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def _webhook_notification_flow(self, payload):
        """Send a notification to the webhook, ignore the signature, and check the response."""
        url = self._build_url(WorldlineController._webhook_url)
        with patch(
            "odoo.addons.payment_worldline.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
        ):
            response = self._make_json_request(url, data=payload)
        self.assertEqual(
            response.json(),
            "",
            msg="The webhook should always respond ''.",
        )

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_webhook_notification_confirms_transaction(self):
        """Test the processing of a webhook notification."""
        tx = self._create_transaction("redirect")
        self.assertFalse(tx.tokenize, "No token should be asked.")
        self._webhook_notification_flow(self.payment_data)
        self.assertFalse(tx.token_id, "No token should be created.")
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, "1234567890")

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_webhook_notification_creates_token(self):
        """Test the processing of a webhook notification when creating a token."""
        tx = self._create_transaction("redirect", tokenize=True)
        self.assertTrue(tx.tokenize, "A token should be asked.")
        self._webhook_notification_flow(self.payment_data)
        self.assertEqual(tx.state, "done")
        self.assertFalse(tx.tokenize, "No token should be asked any more.")
        self.assertTrue(
            tx.token_id, "A token should have been created and linked to the tx."
        )
        self.assertEqual(tx.token_id.provider_ref, "whateverToken")
        self.assertEqual(tx.token_id.payment_details, "4242")

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_failed_webhook_notification_set_tx_as_error_1(self):
        """Test the processing of a webhook notification for a failed transaction."""
        tx = self._create_transaction("redirect")
        test = self.payment_data_insufficient_funds
        self._webhook_notification_flow(test)
        self.assertEqual(tx.state, "error")
        self.assertEqual(
            tx.state_message,
            "Transaction declined with error code 30511001.",
        )

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_failed_webhook_notification_set_tx_as_error_2(self):
        """Test the processing of a webhook notification for a failed transaction."""
        tx = self._create_transaction("redirect")
        test = self.payment_data_expired_card
        self._webhook_notification_flow(test)
        self.assertEqual(tx.state, "error")
        self.assertEqual(
            tx.state_message,
            "Transaction declined with error code 30331001.",
        )

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_failed_webhook_notification_set_tx_as_cancel(self):
        """Test the processing of a webhook notification for a cancelled transaction."""
        tx = self._create_transaction("redirect")
        test = {
            "payment": {
                "paymentOutput": self.payment_data["payment"]["paymentOutput"],
                "hostedCheckoutSpecificOutput": {
                    "hostedCheckoutId": "123456789",
                },
                "status": "CANCELLED",
                "statusOutput": {
                    "errors": [
                        {
                            "errorCode": "30171001",
                        }
                    ],
                },
            },
        }
        self._webhook_notification_flow(test)
        self.assertEqual(tx.state, "cancel")
        self.assertEqual(
            tx.state_message,
            "Transaction cancelled with error code 30171001.",
        )

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_webhook_notification_triggers_signature_check(self):
        """Test that receiving a webhook notification triggers a signature check."""
        self._create_transaction("redirect")
        url = self._build_url(WorldlineController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_worldline.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_json_request(url, data=self.payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_notification_with_valid_signature(self):
        """Test the verification of a notification with a valid signature."""
        tx = self._create_transaction("redirect")
        unencoded_result = hmac.new(
            self.worldline.worldline_webhook_secret.encode(),
            json_dumps_bytes(self.payment_data),
            hashlib.sha256,
        ).digest()
        expected_signature = b64encode(unencoded_result)
        self.assertTrue(
            tx._is_worldline_signature_valid(
                json_dumps_bytes(self.payment_data), expected_signature
            )
        )

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_reject_notification_with_missing_signature(self):
        """Test the verification of a notification with a missing signature."""
        tx = self._create_transaction("redirect")
        self.assertFalse(
            tx._is_worldline_signature_valid(json_dumps_bytes(self.payment_data), None)
        )

    @mute_logger("odoo.addons.payment_worldline.models.payment_transaction")
    def test_reject_notification_with_invalid_signature(self):
        """Test the verification of a notification with an invalid signature."""
        tx = self._create_transaction("redirect")
        self.assertFalse(
            tx._is_worldline_signature_valid(
                json_dumps_bytes(self.payment_data), "dummy"
            )
        )

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_a_malformed_webhook_body_is_refused_without_a_traceback(self):
        url = self._build_url(WorldlineController._webhook_url)
        for body, status in (
            ("not json", 400),
            ([], 400),
            ({"paymentResult": []}, 200),
            ({"payment": {"paymentOutput": "output"}}, 200),
        ):
            with self.subTest(body=body):
                self.assertEqual(
                    self._post_malformed_json(url, body).status_code, status
                )

    @mute_logger("odoo.addons.payment_worldline.controllers.main")
    def test_a_return_that_names_no_provider_or_checkout_is_forbidden_without_a_traceback(
        self,
    ):
        url = self._build_url(WorldlineController._return_url)
        for params in ({}, {"provider_id": "abc"}, {"provider_id": self.provider.id}):
            with self.subTest(params=params):
                with self._assertNoTracebackLogged():
                    response = self.url_open(url, params=params)
                self.assertEqual(response.status_code, 403)

    @mute_logger(
        "odoo.addons.payment_worldline.controllers.main",
        "odoo.addons.payment.models.payment_provider",
    )
    def test_a_return_sends_only_a_well_formed_checkout_id_into_the_api_path(self):
        url = self._build_url(WorldlineController._return_url)
        response = Response()
        response.status_code = 200
        response._content = b"{}"
        for checkout_id, is_sent in (
            ("4134003", True),
            ("../x", False),
            ("..", False),
            ("a/b?c", False),
            ("a%2Fb", False),
            ("a#b", False),
        ):
            with self.subTest(checkout_id=checkout_id):
                with patch.object(
                    GuardedSession, "request", return_value=response
                ) as sent:
                    self.url_open(
                        url,
                        params={
                            "provider_id": self.provider.id,
                            "hostedCheckoutId": checkout_id,
                        },
                        allow_redirects=False,
                    )
                expected_url = self.provider._prepare_request_url(
                    f"hostedcheckouts/{checkout_id}"
                )
                self.assertEqual(
                    [call.args[1] for call in sent.call_args_list],
                    [expected_url] if is_sent else [],
                )

    def test_the_secrets_are_system_only_credentials(self):
        for field_name in ("worldline_api_secret", "worldline_webhook_secret"):
            with self.subTest(field_name=field_name):
                field = self.env["payment.provider"]._fields[field_name]
                self.assertEqual(field.groups, "base.group_system")
                self.assertEqual(field.classification, "secret.credential")
