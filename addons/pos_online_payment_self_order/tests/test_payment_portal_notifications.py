from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.pos_self_order.tests.self_order_common_test import SelfOrderCommonTest


@tagged("post_install", "-at_install")
class TestPaymentPortalNotifications(SelfOrderCommonTest):
    def setUp(self):
        super().setUp()
        self.pos_config.write(
            {
                "self_ordering_mode": "mobile",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
            }
        )
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        self.order = self.env["pos.order"].create(
            {
                "session_id": self.pos_config.current_session_id.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
                "email": "customer@example.com",
                "internal_note": "a note for the staff",
                "lines": [
                    Command.create(
                        {
                            "product_id": self.cola.id,
                            "qty": 1,
                            "price_unit": 10,
                            "price_subtotal": 10,
                            "price_subtotal_incl": 10,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        self.order._recompute_amounts()
        self.sent = []
        Bus = type(self.env["bus.bus"])
        sendone = Bus._sendone

        def record(bus, target, notification_type, message):
            self.sent.append((target, repr(message)))
            return sendone(bus, target, notification_type, message)

        patcher = patch.object(Bus, "_sendone", record)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _online_payment_messages(self):
        return [(t, m) for t, m in self.sent if "'status'" in m]

    def test_an_unauthenticated_confirmation_sends_nothing(self):
        self.url_open(f"/pos/pay/confirmation/{self.order.id}")
        self.url_open(f"/pos/pay/confirmation/{self.order.id}?tx_id=1")

        self.assertEqual(self._online_payment_messages(), [])

    def test_an_unauthenticated_payment_page_sends_nothing(self):
        self.url_open(f"/pos/pay/{self.order.id}?access_token=not-the-token")

        self.assertEqual(self._online_payment_messages(), [])

    def test_the_order_goes_to_its_own_channel_and_the_till_gets_its_id(self):
        self.url_open(
            f"/pos/pay/{self.order.id}?access_token={self.order._receipt_token()}"
        )

        sent = dict(self._online_payment_messages())
        self.assertEqual(
            set(sent), {self.pos_config.access_token, self.order.self_order_channel}
        )
        till = sent[self.pos_config.access_token]
        self.assertNotIn(self.order.access_token, till)
        self.assertNotIn("customer@example.com", till)
        self.assertIn(self.order.access_token, sent[self.order.self_order_channel])
