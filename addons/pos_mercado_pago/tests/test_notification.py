import hashlib
import hmac
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon
from odoo.addons.pos_mercado_pago.models.mercado_pago_pos_request import (
    MercadoPagoPosRequest,
)


@tagged("post_install", "-at_install")
class TestMercadoPagoNotification(HttpCase):
    @mute_logger("odoo.addons.pos_mercado_pago.models.pos_payment_method")
    def test_a_notification_that_names_no_payment_intent_is_refused(self):
        for body in (
            [1],
            "intent",
            {"additional_info": []},
            {"additional_info": "1_1_uuid"},
            {"additional_info": {"external_reference": 5}},
            {"additional_info": {"external_reference": ["1_1_uuid"]}},
        ):
            with self.subTest(body=body):
                response = self.url_open(
                    "/pos_mercado_pago/notification",
                    data=json_dumps(body),
                    headers={
                        "Content-Type": "application/json",
                        "X-Request-Id": "request",
                        "X-Signature": "ts=1,v1=0a",
                    },
                )
                self.assertEqual(response.status_code, 400)


@tagged("post_install", "-at_install")
class TestMercadoPagoWebhookSecret(TestPointOfSaleHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.without_secret, cls.with_secret = cls.env["pos.payment.method"].create(
            [
                {
                    "name": name,
                    "use_payment_terminal": "mercado_pago",
                    "payment_method_type": "terminal",
                    "journal_id": cls.bank_journal.id,
                }
                for name in ("Mercado Pago without secret", "Mercado Pago")
            ]
        )
        cls.with_secret.mp_webhook_secret_key = "webhook secret"
        cls.main_pos_config.write(
            {
                "payment_method_ids": [
                    Command.link(cls.without_secret.id),
                    Command.link(cls.with_secret.id),
                ]
            }
        )
        cls.main_pos_config.with_user(cls.pos_user).open_ui()
        cls.main_pos_config.current_session_id.set_opening_control(0, "")

    def _post_signed_with(self, method, key):
        session = self.main_pos_config.current_session_id
        body = {
            "id": "event",
            "additional_info": {
                "external_reference": f"{session.id}_{method.id}_"
                "6d614b06-4277-4078-aa83-57193658060f"
            },
        }
        signature = hmac.new(
            key.encode(), b"id:event;request-id:request;ts:1;", hashlib.sha256
        ).hexdigest()
        return self.url_open(
            "/pos_mercado_pago/notification",
            data=json_dumps(body),
            headers={
                "Content-Type": "application/json",
                "X-Request-Id": "request",
                "X-Signature": f"ts=1,v1={signature}",
            },
        )

    @mute_logger("odoo.addons.integration.models.integration_receiver")
    def test_a_notification_is_refused_while_no_secret_is_set(self):
        self.assertFalse(self.without_secret.mp_webhook_secret_key)
        response = self._post_signed_with(self.without_secret, "")
        self.assertNotEqual(response.status_code, 200)

    def test_a_notification_signed_with_the_secret_is_accepted(self):
        response = self._post_signed_with(self.with_secret, "webhook secret")
        self.assertEqual(response.status_code, 200)


@tagged("post_install", "-at_install")
class TestMercadoPagoPaymentLookup(TestPointOfSaleHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mercado_pago = cls.env["pos.payment.method"].create(
            {
                "name": "Mercado Pago lookup",
                "use_payment_terminal": "mercado_pago",
                "payment_method_type": "terminal",
                "journal_id": cls.bank_journal.id,
            }
        )
        cls.mercado_pago.mp_id_point_smart_complet = "PAX_A910__SMARTPOS1"

    def _mercado_pago_answers(self, intent_device):
        calls = []

        def call(request, method, endpoint, payload):
            calls.append((method, endpoint))
            if endpoint.startswith("/point/integration-api/payment-intents/"):
                return {
                    "id": endpoint.rsplit("/", 1)[1],
                    "state": "FINISHED",
                    "device_id": intent_device,
                    "payment": {"id": 99},
                }
            return {"id": 99, "status": "approved"}

        return calls, patch.object(MercadoPagoPosRequest, "call_mercado_pago", call)

    def test_the_payment_of_an_intent_of_this_terminal_is_read(self):
        calls, answers = self._mercado_pago_answers("PAX_A910__SMARTPOS1")
        with answers:
            payment = self.mercado_pago.with_user(self.pos_user).mp_get_payment_status(
                "intent-1"
            )
        self.assertEqual(payment["status"], "approved")
        self.assertEqual(calls[-1], ("get", "/v1/payments/99"))

    def test_the_payment_of_another_terminal_is_not_read(self):
        calls, answers = self._mercado_pago_answers("PAX_A910__ELSEWHERE")
        with answers, self.assertRaises(AccessError):
            self.mercado_pago.with_user(self.pos_user).mp_get_payment_status("intent-1")
        self.assertNotIn(("get", "/v1/payments/99"), calls)

    def test_an_intent_id_cannot_leave_the_payment_intent_path(self):
        calls, answers = self._mercado_pago_answers("PAX_A910__SMARTPOS1")
        method = self.mercado_pago.with_user(self.pos_user)
        for call in (
            method.mp_payment_intent_get,
            method.mp_get_payment_status,
            method.mp_payment_intent_cancel,
        ):
            with self.subTest(call=call.__name__), answers:
                with self.assertRaises(UserError):
                    call("../../../users/me")
        self.assertFalse(calls)
