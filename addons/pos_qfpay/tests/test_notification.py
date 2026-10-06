from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestQFPayNotification(HttpCase):
    @mute_logger("odoo.addons.pos_qfpay.models.pos_payment_method")
    def test_a_notification_that_names_no_trade_is_acknowledged(self):
        for body in (
            "not json",
            "[1]",
            '"trade"',
            json_dumps({"out_trade_no": 5}),
            json_dumps({"out_trade_no": ["uuid--1--1"]}),
            json_dumps({"orig_out_trade_no": {"uuid": 1}}),
            json_dumps({"out_trade_no": "uuid--1"}),
        ):
            with self.subTest(body=body):
                response = self.url_open(
                    "/qfpay/notify",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json())
