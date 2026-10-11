from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment_aps.controllers.main import APSController
from odoo.addons.payment_aps.tests.common import APSCommon


@tagged("post_install", "-at_install")
class TestProcessingFlows(APSCommon):
    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_redirect_notification_triggers_processing(self):
        self._create_transaction(flow="redirect")
        url = self._build_url(APSController._return_url)
        with (
            patch(
                "odoo.addons.payment_aps.models.payment_transaction.PaymentTransaction._is_notification_signature_valid"
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_http_post_request(url, data=self.payment_data)
            self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_webhook_notification_triggers_processing(self):
        self._create_transaction("redirect")
        url = self._build_url(APSController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_aps.models.payment_transaction.PaymentTransaction._is_notification_signature_valid"
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_http_post_request(url, data=self.payment_data)
            self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_redirect_notification_triggers_signature_check(self):
        self._create_transaction("redirect")
        url = self._build_url(APSController._return_url)
        with (
            patch(
                "odoo.addons.payment_aps.models.payment_transaction.PaymentTransaction._is_notification_signature_valid"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_http_post_request(url, data=self.payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_webhook_notification_triggers_signature_check(self):
        self._create_transaction("redirect")
        url = self._build_url(APSController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_aps.models.payment_transaction.PaymentTransaction._is_notification_signature_valid"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_http_post_request(url, data=self.payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_notification_with_valid_signature(self):
        tx = self._create_transaction("redirect")
        self.assertTrue(tx._is_notification_signature_valid(self.payment_data))

    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_reject_notification_with_missing_signature(self):
        tx = self._create_transaction("redirect")
        payload = dict(self.payment_data, signature=None)
        self.assertFalse(tx._is_notification_signature_valid(payload))

    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_reject_notification_with_invalid_signature(self):
        tx = self._create_transaction("redirect")
        payload = dict(self.payment_data, signature="dummy")
        self.assertFalse(tx._is_notification_signature_valid(payload))

    @mute_logger("odoo.addons.payment_aps.models.payment_transaction")
    def test_reject_notification_with_a_non_ascii_signature(self):
        tx = self._create_transaction("redirect")
        payload = dict(self.payment_data, signature="é" * 64)
        self.assertFalse(tx._is_notification_signature_valid(payload))
