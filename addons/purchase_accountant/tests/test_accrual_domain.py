from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccrualDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        vendor = cls.env["res.partner"].create({"name": "Accrual Scope Vendor"})
        product = cls.env["product.product"].create(
            {"name": "Accrual Scope", "type": "consu"}
        )
        cls.confirmed, cls.draft = cls.env["purchase.order"].create(
            [
                {
                    "partner_id": vendor.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_qty": 1.0,
                                "price_unit": 10.0,
                                "name": product.name,
                            }
                        )
                    ],
                }
                for _ in range(2)
            ]
        )
        cls.confirmed.action_confirm()

    def test_a_confirmed_order_line_is_in_accrual_scope(self):
        Line = self.env["purchase.order.line"]
        in_scope = Line.search(
            [
                ("order_id", "in", (self.confirmed | self.draft).ids),
                *Line._get_domain_accrual(),
            ]
        )
        self.assertEqual(self.confirmed.state, "done")
        self.assertEqual(in_scope, self.confirmed.line_ids)
