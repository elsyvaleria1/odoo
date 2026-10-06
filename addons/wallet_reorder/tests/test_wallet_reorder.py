from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWalletReorder(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.issuer = cls.env["res.partner"].create({"name": "Fuel Issuer"})
        cls.account = cls.env["wallet.account"].create(
            {"name": "Fleet fuel", "kind": "fuel", "issuer_id": cls.issuer.id}
        )
        cls.low = cls.env["wallet.card"].create(
            {"number": "LOW", "account_id": cls.account.id}
        )
        cls.fine = cls.env["wallet.card"].create(
            {"number": "FINE", "account_id": cls.account.id}
        )
        before = fields.Datetime.now() - timedelta(minutes=1)
        cls._snapshot(cls.low, 100.0, before)
        cls._snapshot(cls.fine, 900.0, before)
        cls.rules = cls.env["wallet.reorder.rule"].create(
            [
                {"card_id": cls.low.id, "amount_min": 500.0, "amount_max": 1000.0},
                {"card_id": cls.fine.id, "amount_min": 500.0, "amount_max": 1000.0},
            ]
        )
        cls.low_rule, cls.fine_rule = cls.rules

    @classmethod
    def _snapshot(cls, card, amount, when=None):
        return cls.env["wallet.balance"].create(
            {
                "card_id": card.id,
                "amount_balance": amount,
                "date": when or fields.Datetime.now(),
            }
        )

    def test_the_rule_reads_the_card_and_the_account(self):
        self.assertEqual(self.low_rule.amount_to_reload, 900.0)
        self.assertEqual(self.low_rule.state, "reorder")
        self.assertEqual(self.fine_rule.amount_to_reload, 0.0)
        self.assertEqual(self.fine_rule.state, "ok")
        self.assertEqual(
            self.low_rule.product_id,
            self.env.ref("wallet_reorder.product_wallet_reload"),
        )
        self.assertEqual(self.low.amount_to_reload, 900.0)

    def test_a_maximum_under_the_minimum_is_refused(self):
        with self.assertRaises(ValidationError):
            self.low_rule.amount_max = 10.0

    def test_the_cron_orders_the_top_up_from_the_issuer_once(self):
        orders = self.env["wallet.reorder.rule"]._cron_procure()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders.partner_id, self.issuer)
        self.assertEqual(orders.state, "draft")
        line = orders.line_ids
        self.assertEqual(len(line), 1)
        self.assertEqual(line.wallet_reorder_rule_id, self.low_rule)
        self.assertEqual(line.wallet_card_id, self.low)
        self.assertEqual(line.price_unit, 900.0)
        self.assertEqual(line.product_qty, 1.0)
        self.assertEqual(self.low_rule.state, "ordered")
        self.assertFalse(
            self.env["wallet.reorder.rule"]._cron_procure(),
            "a top-up still in draft is not ordered twice",
        )
        orders.action_confirm()
        self.low_rule.invalidate_recordset()
        self.assertEqual(self.low_rule.state, "ordered")
        self.assertFalse(
            self.env["wallet.reorder.rule"]._cron_procure(),
            "a confirmed top-up counts until a newer snapshot arrives",
        )
        self._snapshot(self.low, 950.0, fields.Datetime.now() + timedelta(minutes=1))
        self.assertEqual(self.low_rule.state, "ok")
        self._snapshot(self.low, 200.0, fields.Datetime.now() + timedelta(minutes=2))
        self.assertEqual(self.low_rule.state, "reorder")
        again = self.env["wallet.reorder.rule"]._cron_procure()
        self.assertEqual(len(again), 1)
        self.assertEqual(again.line_ids.price_unit, 800.0)

    def test_two_accounts_get_two_orders(self):
        other_issuer = self.env["res.partner"].create({"name": "Toll Issuer"})
        other_account = self.env["wallet.account"].create(
            {"name": "Fleet toll", "kind": "toll", "issuer_id": other_issuer.id}
        )
        tag = self.env["wallet.card"].create(
            {"number": "TAG", "account_id": other_account.id}
        )
        self._snapshot(tag, 10.0)
        self.env["wallet.reorder.rule"].create(
            {"card_id": tag.id, "amount_min": 100.0, "amount_max": 300.0}
        )
        orders = self.env["wallet.reorder.rule"]._cron_procure()
        self.assertEqual(len(orders), 2)
        self.assertEqual(
            sorted(orders.mapped("partner_id.name")), ["Fuel Issuer", "Toll Issuer"]
        )

    def test_a_rule_without_a_product_refuses_to_order(self):
        self.account.reload_product_id = False
        self.low_rule.product_id = False
        with self.assertRaises(ValidationError):
            self.low_rule._procure()
