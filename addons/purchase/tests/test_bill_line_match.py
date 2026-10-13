from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBillLineMatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Match vendor"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Matched part",
                "type": "consu",
                "purchase_ok": True,
                "standard_price": 10.0,
            }
        )
        cls.Match = cls.env["purchase.bill.line.match"]

    def _confirmed_order(self, qty=3, price=10.0):
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "price_unit": price,
                        }
                    )
                ],
            }
        )
        order.action_confirm()
        self.env.flush_all()
        return order

    def _rows(self):
        return self.Match.search([("partner_id", "=", self.vendor.id)])

    def test_confirmed_order_line_awaits_matching(self):
        order = self._confirmed_order()
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.product_uom_qty, 3.0)
        self.assertEqual(rows.product_uom_price, 10.0)
        self.assertEqual(rows.order_line_id, order.line_ids)

    def test_draft_order_is_not_offered_for_matching(self):
        self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 2,
                        }
                    )
                ],
            }
        )
        self.env.flush_all()
        self.assertFalse(self._rows())

    def test_editing_the_price_writes_back_to_the_order_line(self):
        order = self._confirmed_order()
        row = self._rows()
        row.product_uom_price = 12.0
        self.assertEqual(order.line_ids.price_unit, 12.0)

    def test_editing_the_quantity_preserves_the_agreed_price(self):
        order = self._confirmed_order(qty=3, price=10.0)
        row = self._rows()
        row.product_uom_price = 12.0
        row.product_uom_qty = 5.0
        self.assertEqual(order.line_ids.product_qty, 5.0)
        self.assertEqual(order.line_ids.price_unit, 12.0)

    def test_row_opens_its_purchase_order(self):
        order = self._confirmed_order()
        action = self._rows().action_view_line()
        self.assertEqual(action["res_model"], "purchase.order")
        self.assertEqual(action["res_id"], order.id)

    def test_bill_creation_uses_the_lines_currency(self):
        order = self._confirmed_order()
        action = self.Match._action_create_invoice_from_order_lines(
            self.vendor, order.line_ids
        )
        bill = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(bill.move_type, "in_invoice")
        self.assertEqual(bill.partner_id, self.vendor)
        self.assertEqual(bill.currency_id, order.line_ids.currency_id)
        self.assertEqual(bill.invoice_line_ids.product_id, self.product)

    def test_an_order_line_partly_on_a_draft_bill_stays_offered(self):
        self.product.bill_policy = "ordered"
        order = self._confirmed_order(qty=10)
        bill = order.create_invoice()
        bill.invoice_line_ids.quantity = 4
        self.env.flush_all()
        self.assertEqual(order.line_ids.qty_invoiced_draft, 4.0)
        self.assertEqual(order.line_ids.qty_to_invoice, 6.0)
        self.assertEqual(self._rows().order_line_id, order.line_ids)

    def test_an_order_line_wholly_on_a_draft_bill_leaves_the_match_list(self):
        self.product.bill_policy = "ordered"
        order = self._confirmed_order(qty=10)
        order.create_invoice()
        self.env.flush_all()
        self.assertEqual(order.line_ids.qty_invoiced_draft, 10.0)
        self.assertFalse(self._rows().order_line_id)
