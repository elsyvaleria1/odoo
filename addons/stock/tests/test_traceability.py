from datetime import datetime

from odoo.tests import tagged

from odoo.addons.stock.tests.common import TestStockCommon


@tagged("post_install", "-at_install")
class TestStockTraceabilityReport(TestStockCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.env["stock.traceability.report"]
        cls.tracked = cls.env["product.product"].create(
            {"name": "Traced", "is_storable": True, "tracking": "lot"}
        )
        cls.lot = cls.env["product.trace"].create(
            {"name": "LOT-TRC", "product_id": cls.tracked.id}
        )

    def _done_move_line(self, src, dst, date):
        move = self.env["stock.move"].create(
            {
                "product_id": self.tracked.id,
                "product_uom_qty": 5,
                "location_id": src.id,
                "location_dest_id": dst.id,
            }
        )
        line = self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "product_id": self.tracked.id,
                "trace_id": self.lot.id,
                "location_id": src.id,
                "location_dest_id": dst.id,
                "quantity": 5,
            }
        )
        move.state = "done"
        line.date = date
        return line

    def _create_move_line_chain(self):
        ml1 = self._done_move_line(
            self.supplier_location, self.stock_location, datetime(2026, 1, 1)
        )
        ml2 = self._done_move_line(
            self.stock_location, self.shelf_1, datetime(2026, 2, 1)
        )
        ml3 = self._done_move_line(
            self.shelf_1, self.customer_location, datetime(2026, 3, 1)
        )
        return ml1, ml2, ml3

    def test_upstream_move_lines_are_one_level_up(self):
        ml1, ml2, ml3 = self._create_move_line_chain()
        upstream = self.report._get_upstream_move_lines(ml1 | ml2 | ml3)
        self.assertEqual(upstream[ml3.id], ml2)
        self.assertEqual(upstream[ml2.id], ml1)
        self.assertFalse(upstream[ml1.id])

    def test_unfolding_costs_the_same_queries_whatever_the_line_count(self):
        def picking_with_lines(count):
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": self.picking_type_out.id,
                    "location_id": self.shelf_1.id,
                    "location_dest_id": self.customer_location.id,
                }
            )
            for day in range(1, count + 1):
                self._done_move_line(
                    self.stock_location, self.shelf_1, datetime(2026, 1, day)
                )
                line = self._done_move_line(
                    self.shelf_1, self.customer_location, datetime(2026, 2, day)
                )
                line.move_id.picking_id = picking
            return picking

        pickings = {size: picking_with_lines(size) for size in (3, 12)}

        def unfold(size):
            lines = self.report.with_context(
                model="stock.picking", active_id=pickings[size].id
            ).get_lines()
            self.assertEqual(len(lines), size)
            self.assertTrue(all(line["unfoldable"] for line in lines))

        self.assertQueriesConstant(unfold, small=3, large=12)

    def test_row_ids_are_deterministic(self):
        self._create_move_line_chain()
        ctx = {"active_id": self.lot.id, "model": "product.trace"}
        first = self.report.with_context(**ctx).get_lines()
        second = self.report.with_context(**ctx).get_lines()
        self.assertTrue(first, "the lot has done move lines to report")
        ids = [line["id"] for line in first]
        self.assertEqual(ids, [line["id"] for line in second])
        self.assertEqual(ids, list(range(1, len(first) + 1)))

    def test_get_lines_tolerates_partial_kwargs(self):
        result = self.report.with_context(model="product.trace").get_lines(level=2)
        self.assertEqual(result, [])
