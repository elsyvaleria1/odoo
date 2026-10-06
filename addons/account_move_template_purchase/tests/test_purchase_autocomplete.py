from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseAutoComplete(TransactionCase):
    def test_a_purchase_order_set_on_a_bill_fills_it(self):
        vendor = self.env["res.partner"].create({"name": "Autocomplete Vendor"})
        product = self.env["product.product"].create({"name": "Autocomplete Widget"})
        order = self.env["purchase.order"].create(
            {
                "partner_id": vendor.id,
                "line_ids": [
                    Command.create(
                        {"product_id": product.id, "product_qty": 3, "price_unit": 10}
                    )
                ],
            }
        )
        order.action_confirm()
        order.line_ids.qty_transferred = 3

        result = self.env["account.move"].onchange(
            {"move_type": "in_invoice", "purchase_id": order.id},
            ["purchase_id"],
            {
                "move_type": {},
                "purchase_id": {},
                "partner_id": {},
                "invoice_line_ids": {"fields": {"product_id": {}}},
            },
        )

        values = result["value"]
        self.assertEqual(values.get("partner_id"), vendor.id)
        created = [
            command[2]["product_id"]
            for command in values.get("invoice_line_ids", [])
            if command[0] == Command.CREATE
        ]
        self.assertEqual(created, [product.id])
