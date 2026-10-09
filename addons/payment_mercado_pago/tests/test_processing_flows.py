from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_mercado_pago import const
from odoo.addons.payment_mercado_pago.tests.common import MercadoPagoCommon


@tagged("post_install", "-at_install")
class TestProcessingFlows(MercadoPagoCommon, PaymentHttpCommon):
    @mute_logger("odoo.addons.payment_mercado_pago.controllers.main")
    def test_redirect_notification_triggers_processing(self):
        """Test that receiving a redirect notification triggers the processing of the notification
        data."""
        self._create_transaction(flow="redirect")
        url = self._build_url(const.PAYMENT_RETURN_ROUTE)
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

    @mute_logger("odoo.addons.payment_mercado_pago.controllers.main")
    def test_webhook_notification_triggers_processing(self):
        """Test that receiving a valid webhook notification triggers the processing of the
        payment data."""
        tx = self._create_transaction(flow="redirect")
        url = self._build_url(f"{const.WEBHOOK_ROUTE}/{tx.reference}")
        with (
            patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
                return_value=self.verification_data,
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_json_request(url, data=self.webhook_payment_data)
        self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_a_malformed_webhook_body_is_refused_without_a_traceback(self):
        url = self._build_url(f"{const.WEBHOOK_ROUTE}/unknown-reference")
        for body, status in (
            ("not json", 400),
            ([], 400),
            ({"action": "payment.created", "data": []}, 200),
        ):
            with self.subTest(body=body):
                self.assertEqual(
                    self._post_malformed_json(url, body).status_code, status
                )

    def _get_approved_payment_of(self, tx, external_reference):
        return {
            "id": self.payment_id,
            "status": "approved",
            "external_reference": external_reference,
            "currency_id": tx.currency_id.name,
            "additional_info": {"items": [{"unit_price": tx.amount}]},
        }

    @mute_logger(
        "odoo.addons.payment_mercado_pago.controllers.payment",
        "odoo.addons.payment.models.payment_transaction",
    )
    def test_a_payment_of_another_transaction_is_refused(self):
        tx = self._create_transaction(flow="redirect")
        other_payment = self._get_approved_payment_of(tx, "another-reference")
        for send in (
            lambda: self._make_http_get_request(
                self._build_url(const.PAYMENT_RETURN_ROUTE),
                params=self.redirect_payment_data,
            ),
            lambda: self._make_json_request(
                self._build_url(f"{const.WEBHOOK_ROUTE}/{tx.reference}"),
                data=self.webhook_payment_data,
            ),
        ):
            with patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
                return_value=other_payment,
            ):
                response = send()
            tx.invalidate_recordset()
            self.assertEqual(response.status_code, 403)
            self.assertEqual(tx.state, "draft")

    @mute_logger("odoo.addons.payment_mercado_pago.controllers.payment")
    def test_the_payment_of_the_transaction_is_processed(self):
        tx = self._create_transaction(flow="redirect")
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value=self._get_approved_payment_of(tx, tx.reference),
        ):
            self._make_http_get_request(
                self._build_url(const.PAYMENT_RETURN_ROUTE),
                params=self.redirect_payment_data,
            )
        tx.invalidate_recordset()
        self.assertEqual(tx.state, "done")

    @mute_logger("odoo.addons.payment_mercado_pago.controllers.payment")
    def test_a_payment_id_that_is_no_number_is_refused_unfetched(self):
        self._create_transaction(flow="redirect")
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
        ) as send_mock:
            response = self._make_http_get_request(
                self._build_url(const.PAYMENT_RETURN_ROUTE),
                params=dict(self.redirect_payment_data, payment_id="1/../../users/me"),
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(send_mock.called)
