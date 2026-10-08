import logging

from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosDiscountSaleDetails(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.discount_product = self.env["product.product"].create(
            {"name": "Global discount", "type": "service", "taxes_id": False}
        )
        self.config.write(
            {
                "module_pos_discount": True,
                "discount_product_id": self.discount_product.id,
            }
        )
        self.product = self.create_product("Discounted", self.categ_basic, 100)
        self.config.open_ui()
        self.session = self.config.current_session_id
        self.report = self.env["report.point_of_sale.report_saledetails"]

    def _paid_order(self, *lines, **values):
        order = self.env["pos.order"].create(
            {
                "session_id": self.session.id,
                "company_id": self.env.company.id,
                "amount_paid": 0,
                "amount_total": 0,
                "amount_tax": 0,
                "amount_return": 0,
                "lines": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "qty": qty,
                            "price_unit": price,
                            "price_subtotal": 0,
                            "price_subtotal_incl": 0,
                            "tax_ids": [Command.clear()],
                            **line_values,
                        }
                    )
                    for product, qty, price, line_values in lines
                ],
                **values,
            }
        )
        order.lines._onchange_amount_line_all()
        order._onchange_amount_all()
        self.make_payment(order, self.cash_pm1, order.amount_total)
        return order

    def _sold_and_refunded(self):
        report = self.report.get_sale_details(session_ids=self.session.ids)
        rows = {
            section: sorted(
                (row["product_name"], row["quantity"], row["total_paid"])
                for category in report[section]
                for row in category["products"]
            )
            for section in ("products", "refund_products")
        }
        _logger.debug("Sale details with a global discount: %s", rows)
        return report, rows

    def test_a_refund_with_a_global_discount_refunds_the_discounted_amount(self):
        sale = self._paid_order(
            (self.product, 1, 100, {}), (self.discount_product, 1, -10, {})
        )
        # the ticket screen does not refund the discount line: it applies the
        # global discount again to the refund, which yields quantity 1, price 10
        self._paid_order(
            (self.product, -1, 100, {"refunded_orderline_id": sale.lines[0].id}),
            (self.discount_product, 1, 10, {}),
            is_refund=True,
        )

        report, rows = self._sold_and_refunded()

        self.assertEqual(
            rows["products"], [("Discounted", 1, 100), ("Global discount", 1, -10)]
        )
        self.assertEqual(
            rows["refund_products"],
            [("Discounted", 1, 100), ("Global discount", -1, -10)],
        )
        self.assertEqual(report["products_info"]["total"], 90)
        self.assertEqual(report["refund_info"]["total"], 90)

    def test_a_refunded_discount_line_stays_a_refund(self):
        sale = self._paid_order(
            (self.product, 1, 100, {}), (self.discount_product, 1, -10, {})
        )
        refund = sale._refund()
        self.make_payment(refund, self.cash_pm1, refund.amount_total)

        report, rows = self._sold_and_refunded()

        self.assertEqual(
            rows["refund_products"],
            [("Discounted", 1, 100), ("Global discount", 1, -10)],
        )
        self.assertEqual(report["products_info"]["total"], 90)
        self.assertEqual(report["refund_info"]["total"], 90)
