from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccrualReadGroup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Line = cls.env["purchase.order.line"]
        cls.vendor = cls.env["res.partner"].create({"name": "Accrual Vendor"})
        cls.product_a = cls.env["product.product"].create(
            {"name": "Accrual A", "type": "consu"}
        )
        cls.product_b = cls.env["product.product"].create(
            {"name": "Accrual B", "type": "consu"}
        )
        cls.order = cls.env["purchase.order"].create(
            {
                "partner_id": cls.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": qty,
                            "price_unit": 10.0,
                            "name": product.name,
                        }
                    )
                    for product, qty in ((cls.product_a, 2.0), (cls.product_b, 7.0))
                ],
            }
        )

    def setUp(self):
        super().setUp()
        Model = type(self.Line)
        self.patch(Model, "_get_domain_accrual", lambda records: [])

        def qty_is_ordered_qty(records):
            for line in records:
                line.qty_invoiced_at_date = line.product_qty

        self.patch(Model, "_compute_qty_invoiced_at_date", qty_is_ordered_qty)
        self.domain = [("order_id", "=", self.order.id)]
        self.expected = {
            line.product_id: line.qty_invoiced_at_date for line in self.order.line_ids
        }
        self.assertEqual(
            len(set(self.expected.values())), 2, "the fixture must be able to fail"
        )

    def test_each_group_sums_its_own_records(self):
        rows = self.Line._read_group(
            self.domain, ["partner_id", "product_id"], ["qty_invoiced_at_date:sum"]
        )
        self.assertEqual({row[1]: row[2] for row in rows}, self.expected)

    def test_no_grouping_at_all(self):
        rows = self.Line._read_group(self.domain, [], ["qty_invoiced_at_date:sum"])
        self.assertEqual(rows, [(sum(self.expected.values()),)])

    def test_the_patched_aggregate_keeps_its_position(self):
        rows = self.Line._read_group(
            self.domain,
            ["product_id"],
            ["qty_invoiced_at_date:sum", "price_total:sum"],
        )
        self.assertEqual(
            {row[0]: row[1] for row in rows},
            self.expected,
            "the manual sum landed under the wrong aggregate",
        )
