from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosOrderAvgTime(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.env["product.product"].create(
            {"name": "Avg Burger", "available_in_pos": True, "list_price": 10.0}
        )

    def _make_order(self, line_count=2):
        self.config.open_ui()
        session = self.config.current_session_id
        line_vals = [
            Command.create(
                {
                    "product_id": self.product.id,
                    "qty": 1,
                    "price_unit": 10.0,
                    "price_subtotal": 10.0,
                    "price_subtotal_incl": 10.0,
                }
            )
            for _ in range(line_count)
        ]
        return self.env["pos.order"].create(
            {
                "company_id": self.env.company.id,
                "session_id": session.id,
                "lines": line_vals,
                "amount_tax": 0.0,
                "amount_total": 10.0 * line_count,
                "amount_paid": 0.0,
                "amount_return": 0.0,
            }
        )

    def test_avg_times_default_to_sentinel_without_recorded_lines(self):
        """Check that orders whose lines carry no recorded times report the -1
        sentinel averages."""
        order = self._make_order()
        self.assertEqual(order.avg_preparation_time, -1)
        self.assertEqual(order.avg_service_time, -1)

    def test_avg_times_ignore_unrecorded_lines(self):
        """Check that the averages only aggregate lines with recorded times,
        leaving -1 lines out of the mean."""
        order = self._make_order()
        order.lines[0].preparation_time = 120
        order.lines[0].service_time = 30

        self.assertEqual(order.avg_preparation_time, 120)
        self.assertEqual(order.avg_service_time, 30)

    def test_avg_times_average_all_recorded_lines(self):
        """Check that the averages are the mean over every recorded line."""
        order = self._make_order()
        order.lines[0].preparation_time = 100
        order.lines[1].preparation_time = 200
        order.lines[0].service_time = 40
        order.lines[1].service_time = 20

        self.assertEqual(order.avg_preparation_time, 150)
        self.assertEqual(order.avg_service_time, 30)
