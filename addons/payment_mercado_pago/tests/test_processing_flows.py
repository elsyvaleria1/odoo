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

    @mute_logger("odoo.addons.payment_mercado_pago.controllers.payment")
    def test_a_payment_id_in_non_ascii_digits_is_refused_unfetched(self):
        self._create_transaction(flow="redirect")
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
        ) as send_mock:
            response = self._make_http_get_request(
                self._build_url(const.PAYMENT_RETURN_ROUTE),
                params=dict(self.redirect_payment_data, payment_id="²٣"),
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(send_mock.called)

    def _pay_by_card(self, tx, **route_values):
        sent_payments = []

        def charge(_provider, _method, _endpoint, json=None, **_kwargs):
            sent_payments.append(json)
            return {
                "id": 999,
                "status": "approved",
                "external_reference": json["external_reference"],
                "transaction_amount": json["transaction_amount"],
                "currency_id": tx.currency_id.name,
                "additional_info": json["additional_info"],
                "payment_type_id": "credit_card",
                "payment_method_id": "visa",
            }

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            autospec=True,
            side_effect=charge,
        ):
            self.call_jsonrpc(
                "/payment/mercado_pago/payments",
                {
                    "reference": tx.reference,
                    "token": "card-token",
                    "installments": 1,
                    "payment_method_brand": "visa",
                    "issuer_id": "1",
                    **route_values,
                },
            )
        tx.invalidate_recordset()
        return sent_payments

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_a_card_payment_charges_the_amount_of_the_transaction(self):
        tx = self._create_transaction(flow="direct")
        sent_payments = self._pay_by_card(tx, transaction_amount=1)
        self.assertEqual(sent_payments[0]["transaction_amount"], tx.amount)
        self.assertEqual(tx.state, "done")

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_a_card_payment_of_less_than_the_transaction_is_not_done(self):
        tx = self._create_transaction(flow="direct")
        tx._process(
            "mercado_pago",
            {
                "id": 999,
                "status": "approved",
                "external_reference": tx.reference,
                "transaction_amount": 1.0,
                "currency_id": tx.currency_id.name,
                "additional_info": {"items": [{"unit_price": tx.amount}]},
            },
        )
        self.assertEqual(tx.state, "error")

    def _notify_payment(self, tx, payment_id, status):
        payment = dict(
            self._get_approved_payment_of(tx, tx.reference),
            id=payment_id,
            status=status,
        )
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value=payment,
        ):
            response = self._make_json_request(
                self._build_url(f"{const.WEBHOOK_ROUTE}/{tx.reference}"),
                data={"action": "payment.updated", "data": {"id": str(payment_id)}},
            )
        tx.invalidate_recordset()
        return response

    @mute_logger(
        "odoo.addons.payment_mercado_pago.controllers.payment",
        "odoo.addons.payment.models.payment_transaction",
    )
    def test_an_earlier_payment_does_not_move_the_transaction(self):
        tx = self._create_transaction(
            flow="redirect", state="pending", provider_reference="222"
        )
        for status in ("cancelled", "rejected"):
            with self.subTest(status=status):
                response = self._notify_payment(tx, 111, status)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(tx.state, "pending")
                self.assertEqual(tx.provider_reference, "222")

    @mute_logger("odoo.addons.payment_mercado_pago.controllers.payment")
    def test_an_approved_retry_confirms_a_transaction_whose_payment_failed(self):
        tx = self._create_transaction(
            flow="redirect", state="error", provider_reference="111"
        )
        self._notify_payment(tx, 222, "approved")
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, "222")

    @mute_logger(
        "odoo.addons.payment_mercado_pago.controllers.payment",
        "odoo.addons.payment.models.payment_transaction",
    )
    def test_a_refunded_payment_confirms_nothing(self):
        tx = self._create_transaction(flow="redirect")
        self._notify_payment(tx, 111, "refunded")
        self.assertEqual(tx.state, "cancel")

    @mute_logger("odoo.addons.payment_mercado_pago.controllers.payment")
    def test_the_refund_of_a_confirmed_payment_leaves_it_done(self):
        tx = self._create_transaction(
            flow="redirect", state="done", provider_reference="111"
        )
        self._notify_payment(tx, 111, "refunded")
        self.assertEqual(tx.state, "done")
