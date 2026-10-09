from unittest.mock import patch
from urllib.parse import urlencode

from odoo import Command
from odoo.tests import HttpCase, tagged
from odoo.tools import hash_sign, mute_logger

from odoo.addons.point_of_sale.tests.common import CommonPosTest
from odoo.addons.pos_mollie.models.pos_payment_method import (
    WEBHOOK_SCOPE,
    PosPaymentMethod,
)


@tagged("post_install", "-at_install")
class TestMollieWebhook(CommonPosTest, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        provider = cls.env["payment.provider"].create(
            {"name": "Mollie", "code": "mollie", "mollie_api_key": "test_dummy"}
        )
        cls.mollie_method = cls.env["pos.payment.method"].create(
            {
                "name": "Mollie",
                "use_payment_terminal": "mollie",
                "payment_method_type": "terminal",
                "journal_id": cls.bank_payment_method.journal_id.id,
                "mollie_payment_provider_id": provider.id,
                "mollie_terminal_id": "term_1",
            }
        )
        cls.pos_config_usd.write(
            {"payment_method_ids": [Command.link(cls.mollie_method.id)]}
        )

    def setUp(self):
        super().setUp()
        self.pos_config_usd.open_ui()
        self.session = self.pos_config_usd.current_session_id

    def _post_webhook(self, payment_id, payment):
        payload = hash_sign(
            self.env(su=True),
            WEBHOOK_SCOPE,
            {
                "payment_uuid": "uuid-1",
                "payment_method_id": self.mollie_method.id,
                "pos_session_id": self.session.id,
            },
            expiration_hours=27,
        )
        with (
            patch.object(
                PosPaymentMethod,
                "_mollie_get_payment",
                autospec=True,
                return_value=payment,
            ) as get_mock,
            patch.object(
                type(self.env["pos.config"]), "_notify", autospec=True
            ) as notify_mock,
        ):
            response = self.url_open(
                f"/pos_mollie/webhook?{urlencode({'payload': payload})}",
                data={"id": payment_id},
            )
        return response, get_mock, notify_mock

    def _get_paid_payment(self, payment_uuid):
        return {
            "id": "tr_1",
            "status": "paid",
            "description": f"pos_session_id={self.session.id},payment_uuid={payment_uuid}",
            "details": {},
        }

    @mute_logger("odoo.addons.pos_mollie.controllers.webhook")
    def test_the_payment_of_the_signed_payload_reaches_its_session(self):
        response, _get_mock, notify_mock = self._post_webhook(
            "tr_1", self._get_paid_payment("uuid-1")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(notify_mock.call_args.args[2]["status"], "paid")

    @mute_logger("odoo.addons.pos_mollie.controllers.webhook")
    def test_a_payment_the_signed_payload_does_not_name_is_refused(self):
        response, _get_mock, notify_mock = self._post_webhook(
            "tr_1", self._get_paid_payment("another-uuid")
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(notify_mock.called)

    @mute_logger("odoo.addons.pos_mollie.controllers.webhook")
    def test_an_id_that_is_no_mollie_payment_id_is_refused_unfetched(self):
        for payment_id in ("tr_1/refunds", "../methods", ""):
            with self.subTest(payment_id=payment_id):
                response, get_mock, _notify_mock = self._post_webhook(
                    payment_id, self._get_paid_payment("uuid-1")
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(get_mock.called)
