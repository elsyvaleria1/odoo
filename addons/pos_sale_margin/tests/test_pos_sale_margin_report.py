import odoo
from odoo.tools import SQL

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestPoSSaleMarginReport(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _pos_report_margins(self):
        self.env.flush_all()
        report = self.env["sale.report"].sudo()
        query = SQL(
            "SELECT %s FROM %s WHERE %s GROUP BY %s",
            report._select_pos(),
            report._from_pos(),
            report._where_pos(),
            report._group_by_pos(),
        )
        self.env.cr.execute(query)
        cols = [d.name for d in self.env.cr.description]
        margin_index = cols.index("margin")
        return [row[margin_index] for row in self.env.cr.fetchall()]

    def test_pos_sale_margin_report(self):

        product1 = self.create_product(
            "Product 1", self.categ_basic, 150, standard_price=50
        )

        self.open_new_session()
        session = self.pos_session

        self.env["pos.order"].create(
            {
                "session_id": session.id,
                "lines": [
                    (
                        0,
                        0,
                        {
                            "name": "OL/0001",
                            "product_id": product1.id,
                            "price_unit": 450,
                            "discount": 5.0,
                            "qty": 1.0,
                            "price_subtotal": 150,
                            "price_subtotal_incl": 150,
                            "total_cost": 50,
                        },
                    ),
                ],
                "amount_total": 150.0,
                "amount_tax": 0.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
            }
        )

        margins = self._pos_report_margins()
        self.assertEqual(margins, [100])

    def test_pos_sale_margin_report_refund(self):
        product1 = self.create_product(
            "Refund Product", self.categ_basic, 150, standard_price=50
        )

        self.open_new_session()
        session = self.pos_session

        order = self.env["pos.order"].create(
            {
                "session_id": session.id,
                "lines": [
                    (
                        0,
                        0,
                        {
                            "name": "OL/REFUND",
                            "product_id": product1.id,
                            "price_unit": 150,
                            "discount": 0.0,
                            "qty": 1.0,
                            "price_subtotal": 150,
                            "price_subtotal_incl": 150,
                            "total_cost": 50,
                        },
                    ),
                ],
                "amount_total": 150.0,
                "amount_tax": 0.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
            }
        )
        order.lines.is_total_cost_computed = True
        self.assertEqual(order.lines.margin, 100)

        refund_order = order._refund()
        self.assertEqual(refund_order.lines.margin, -200)

        self.assertEqual(sorted(self._pos_report_margins()), [-200, 100])

    def test_pos_sale_margin_uses_currency_table_factor(self):
        expression = self.env["sale.report"]._get_pos_field_expressions({})["margin"]
        self.assertIn("l.margin", expression)
        self.assertIn("account_currency_table.rate", expression)
        self.assertIn("pos.currency_rate", expression)
