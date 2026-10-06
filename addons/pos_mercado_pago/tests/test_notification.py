from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


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
