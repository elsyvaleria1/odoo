from odoo import fields
from odoo.fields import Command
from odoo.tests.common import tagged

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged("post_install", "-at_install")
class TestPoSSubscription(TestPointOfSaleHttpCommon):
    def test_pos_recurring_product_invoicing(self):
        plan_month = (
            self.env["sale.subscription.plan"]
            .sudo()
            .create(
                {
                    "name": "Monthly",
                    "repeat_interval": 1,
                    "repeat_unit": "month",
                    "sequence": 4,
                }
            )
        )
        self.recurring_product_id = self.env["product.product"].create(
            {
                "name": "Test2",
                "available_in_pos": True,
                "recurring_invoice": True,
                "lst_price": 250,
                "taxes_id": False,
            }
        )

        self.sale_order_id = (
            self.env["sale.order"]
            .sudo()
            .create(
                {
                    "partner_id": self.partner_a.id,
                    "plan_id": plan_month.id,
                    "start_date": fields.Date.from_string("2021-01-01"),
                    "next_invoice_date": fields.Date.from_string("2021-01-01"),
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.recurring_product_id.id,
                                "product_qty": 1,
                                "price_unit": 250,
                            }
                        )
                    ],
                }
            )
        )

        self.main_pos_config.with_user(self.pos_user).open_ui()
        current_session = self.main_pos_config.current_session_id

        pos_order = {
            "amount_paid": 250,
            "amount_return": 0,
            "amount_tax": 0,
            "amount_total": 250,
            "date_order": fields.Datetime.to_string(fields.Datetime.now()),
            "fiscal_position_id": False,
            "to_invoice": True,
            "partner_id": self.partner_a.id,
            "pricelist_id": self.main_pos_config.available_pricelist_ids[0].id,
            "lines": [
                [
                    0,
                    0,
                    {
                        "discount": 0,
                        "pack_lot_ids": [],
                        "price_unit": 250,
                        "product_id": self.recurring_product_id.id,
                        "price_subtotal": 250,
                        "price_subtotal_incl": 250,
                        "sale_order_line_id": self.sale_order_id.line_ids[0].id,
                        "sale_order_origin_id": self.sale_order_id.id,
                        "qty": 1,
                        "tax_ids": [],
                    },
                ]
            ],
            "session_id": current_session.id,
            "payment_ids": [
                [
                    0,
                    0,
                    {
                        "amount": 250,
                        "name": fields.Datetime.now(),
                        "payment_method_id": self.main_pos_config.payment_method_ids[
                            0
                        ].id,
                    },
                ]
            ],
            "user_id": self.env.uid,
        }

        self.env["pos.order"].sync_from_ui([pos_order])
        self.assertEqual(self.sale_order_id.line_ids[0].qty_invoiced, 1)
        self.assertEqual(
            self.sale_order_id.next_invoice_date, fields.Date.from_string("2021-02-01")
        )
