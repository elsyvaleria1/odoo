from unittest.mock import patch
from urllib.parse import urlencode as url_encode

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_xendit.controllers.main import XenditController
from odoo.addons.payment_xendit.tests.common import XenditCommon


@tagged("post_install", "-at_install")
class TestProcessingFlow(XenditCommon, PaymentHttpCommon):
    @mute_logger("odoo.addons.payment_xendit.models.payment_transaction")
    def test_webhook_notification_triggers_processing(self):
        self._create_transaction("redirect")
        url = self._build_url(XenditController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_xendit.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_json_request(url, data=self.webhook_payment_data)
        self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_xendit.models.payment_transaction")
    def test_webhook_notification_triggers_signature_check(self):
        self._create_transaction("redirect")
        url = self._build_url(XenditController._webhook_url)
        with patch(
            "odoo.addons.payment_xendit.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
        ) as signature_check_mock:
            self._make_json_request(url, data=self.webhook_payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_webhook_notification_with_valid_signature(self):
        tx = self._create_transaction("redirect")
        self.assertTrue(tx._is_xendit_token_valid(self.provider.xendit_webhook_token))

    @mute_logger("odoo.addons.payment_xendit.models.payment_transaction")
    def test_reject_notification_with_missing_signature(self):
        tx = self._create_transaction("redirect")
        self.assertFalse(tx._is_xendit_token_valid(None))

    @mute_logger("odoo.addons.payment_xendit.models.payment_transaction")
    def test_reject_notification_with_invalid_signature(self):
        tx = self._create_transaction("redirect")
        self.assertFalse(tx._is_xendit_token_valid("dummy"))

    def test_set_xendit_transactions_to_pending_on_return(self):
        def build_return_url(**kwargs):
            url_params = url_encode(dict(kwargs, tx_ref=self.reference))
            return self._build_url(f"{XenditController._return_url}?{url_params}")

        self.reference = "xendit_tx1"
        tx = self._create_transaction("redirect")

        with patch.object(
            payment_utils, "generate_access_token", self._generate_test_access_token
        ):
            token = payment_utils.generate_access_token(tx.reference, tx.amount)

            self._make_http_get_request(
                build_return_url(success="true", access_token="coincoin")
            )
            self.assertEqual(
                tx.state, "draft", "Random GET requests shouldn't affect tx state"
            )

            self._make_http_get_request(
                build_return_url(success="false", access_token=token)
            )
            self.assertEqual(
                tx.state, "draft", "Failure returns shouldn't change tx state"
            )

            self._make_http_get_request(
                build_return_url(success="true", access_token=token)
            )
            self.assertEqual(
                tx.state, "pending", "Successful returns should set state to pending"
            )

    def test_a_malformed_webhook_body_is_refused_without_a_traceback(self):
        url = self._build_url(XenditController._webhook_url)
        for body in ("not json", []):
            with self.subTest(body=body):
                self.assertEqual(self._post_malformed_json(url, body).status_code, 400)
