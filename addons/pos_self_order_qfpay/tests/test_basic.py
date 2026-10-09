from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import Command
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged("post_install", "-at_install")
class TestSelfOrderKioskQFPay(TestPointOfSaleHttpCommon, AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.currency_id = cls.env.ref("base.HKD")
        cls.main_pos_config.use_pricelist = False
        cls.pos_config = cls.env["pos.config"].create(
            {
                "name": "Test HK POS Config",
                "use_presets": False,
                "default_preset_id": False,
                "available_preset_ids": [(5, 0)],
                "self_ordering_mode": "kiosk",
                "self_ordering_pay_after": "each",
                "self_ordering_service_mode": "counter",
                "payment_method_ids": [
                    Command.create(
                        {
                            "name": "Qfpay",
                            "qfpay_pos_key": "my_qfpay_pos_key",
                            "qfpay_notification_key": "my_qfpay_notification_key",
                            "use_payment_terminal": "qfpay",
                            "payment_method_type": "terminal",
                            "qfpay_payment_type": "card_payment",
                            "journal_id": cls.bank_journal.id,
                        }
                    )
                ],
            }
        )

        cls.env["pos.payment.method"].create(
            {
                "name": "Qfpay 2",
                "use_payment_terminal": "qfpay",
            }
        )

    def test_kiosk_qfpay(self):
        res = self.pos_config.load_self_data()
        pm = res.get("pos.payment.method", [])
        self.assertEqual(len(pm), 1, "Only one payment method should be loaded")
        self.assertEqual(
            pm[0]["name"], "Qfpay", "The loaded payment method should be Qfpay"
        )

        after_pay_kds = self.env["pos.config"]._supported_kiosk_payment_terminal()
        self.assertTrue(
            "qfpay" in after_pay_kds,
            "The orders payed with qfpay should be sent to Kitchen Display/Printer only after being paid",
        )

    def test_tour_kiosk_qfpay_order(self):
        self.pos_config.with_user(self.pos_user).open_ui()
        self.pos_config.current_session_id.set_opening_control(0, "")
        self_route = self.pos_config._get_self_order_route()
        with patch.object(
            type(self.env["pos.payment.method"]),
            "_is_inbound_request_authentic",
            lambda self, headers, body: True,
        ):
            self.start_tour(self_route, "kiosk_qfpay_order")

    def _kiosk_order(self):
        self.pos_config.with_user(self.pos_user).open_ui()
        session = self.pos_config.current_session_id
        session.set_opening_control(0, "")
        order = self.env["pos.order"].create(
            {
                "session_id": session.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.desk_pad.product_variant_id.id,
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
        order._recompute_amounts()
        return order

    def test_a_replayed_notification_pays_the_order_once(self):
        qfpay = self.pos_config.payment_method_ids
        order = self._kiosk_order()
        notification = {
            "notify_type": "payment",
            "status": "1",
            "chnlsn": "CHANNEL-1",
            "syssn": "SYSSN-1",
        }

        qfpay._qfpay_handle_webhook(self.pos_config, notification, order.uuid)
        qfpay._qfpay_handle_webhook(self.pos_config, notification, order.uuid)

        self.assertEqual(order.state, "paid")
        self.assertEqual(order.payment_ids.mapped("transaction_id"), ["SYSSN-1"])

    def test_a_notification_in_another_currency_pays_nothing(self):
        qfpay = self.pos_config.payment_method_ids
        order = self._kiosk_order()
        notification = {
            "notify_type": "payment",
            "status": "1",
            "chnlsn": "CHANNEL-1",
            "syssn": "SYSSN-1",
            "txcurrcd": "USD",
        }

        qfpay._qfpay_handle_webhook(self.pos_config, notification, order.uuid)

        self.assertEqual(order.state, "draft")
        self.assertFalse(order.payment_ids)

    def test_a_kiosk_trade_is_signed_only_for_the_orders_amount(self):
        qfpay = self.pos_config.payment_method_ids.with_user(self.pos_user)
        order = self._kiosk_order()
        trade = {
            "func_type": 1001,
            "channel": "card_payment",
            "out_trade_no": f"{order.uuid}--{order.session_id.id}--{qfpay.id}",
        }

        with self.assertRaises(UserError):
            qfpay.qfpay_sign_request({**trade, "amt": 0.1})
        self.assertTrue(qfpay.qfpay_sign_request({**trade, "amt": 10.0}))
