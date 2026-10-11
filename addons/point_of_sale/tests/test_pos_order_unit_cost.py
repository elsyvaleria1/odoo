from odoo import fields
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    PosCashRoundingSessionCommon,
    PosOpenSessionCommon,
    TestPoSCommon,
)


@tagged("post_install", "-at_install", "pos_order_cost")
class TestPosOrderLineCost(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.avco_product = cls.create_product(
            "AVCO Product",
            cls.categ_basic,
            10.0,
            standard_price=5.0,
        )
        cls.avco_product.categ_id.property_cost_method = "average"

    def test_price_cost_is_the_unit_cost_for_several_fifo_avco_lines(self):
        self.open_new_session()
        order = self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [
                        (self.avco_product, 2),
                        (self.avco_product, 3),
                    ],
                    "payments": [(self.cash_pm1, 50)],
                    "uuid": "00100-010-0001",
                }
            ]
        )["00100-010-0001"]

        self.assertEqual(len(order.lines), 2, "a per-line branch needs two lines")
        self.pos_session.action_pos_session_closing_control()

        for line in order.lines:
            self.assertTrue(line.is_total_cost_computed)
            self.assertAlmostEqual(
                line.price_cost,
                line.total_cost / line.qty,
                places=2,
                msg="price_cost is the unit cost behind total_cost",
            )


@tagged("post_install", "-at_install")
class TestPosOrderLineCostConversion(PosCashRoundingSessionCommon):
    def test_cost_uses_order_company_when_active_company_differs(self):
        order = self._create_bare_order()
        line = self._create_line(order)
        other_company = self.env["res.company"].create(
            {"name": "Other costing company"}
        )
        self.env.user.sudo().company_ids += other_company
        line.product_id.with_company(order.company_id).standard_price = 7
        line.product_id.with_company(other_company).standard_price = 17

        line.sudo().with_company(other_company)._update_total_cost(
            self.env["stock.move"]
        )

        self.assertEqual(line.total_cost, 7)
        self.assertEqual(line.price_cost, 7)

    def test_ship_later_refund_does_not_convert_foreign_cost_twice(self):
        company = self.env.company
        euro = self.env.ref("base.EUR")
        self.env["res.currency.rate"].create(
            {
                "currency_id": euro.id,
                "company_id": company.id,
                "name": fields.Date.today(),
                "rate": 2,
            }
        )
        self.pos_config_eur.open_ui()
        order = self._create_bare_order(
            session_id=self.pos_config_eur.current_session_id.id
        )
        original = self._create_line(order)
        original.product_id = self.test_product_order
        original.qty = 2
        original.product_id.standard_price = 10
        original._update_total_cost(self.env["stock.move"])
        self.assertEqual(original.total_cost, 40)
        original.price_cost = 0
        refund = self._create_bare_order(
            session_id=order.session_id.id,
            shipping_date=fields.Date.today(),
            is_refund=True,
        )
        line = self._create_line(refund)
        line.write(
            {
                "product_id": original.product_id.id,
                "qty": -1,
                "refunded_orderline_id": original.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": line.product_id.id,
                "product_uom_id": line.product_uom_id.id,
                "product_uom_qty": 1,
                "location_id": self.env.ref("stock.stock_location_customers").id,
                "location_dest_id": self.company_data[
                    "default_warehouse"
                ].lot_stock_id.id,
            }
        )

        line._update_total_cost(move)

        self.assertEqual(line.total_cost, -20)
        self.assertEqual(line.price_cost, 10)

    def test_refund_cost_preserves_saved_unit_cost_after_rate_correction(self):
        euro = self.env.ref("base.EUR")
        rate = self.env["res.currency.rate"].create(
            {
                "currency_id": euro.id,
                "company_id": self.env.company.id,
                "name": "2026-09-01",
                "rate": 2,
            }
        )
        self.env["res.currency.rate"].create(
            {
                "currency_id": euro.id,
                "company_id": self.env.company.id,
                "name": "2026-09-13",
                "rate": 3,
            }
        )
        self.pos_config_eur.open_ui()
        original = self._create_bare_order(
            session_id=self.pos_config_eur.current_session_id.id,
            date_order="2026-09-01 12:00:00",
        )
        original_line = self._create_line(original)
        original_line.product_id = self.test_product_order
        original_line.product_id.standard_price = 10
        original_line._update_total_cost(self.env["stock.move"])
        self.assertEqual(original_line.total_cost, 20)
        self.assertEqual(original_line.price_cost, 10)
        rate.rate = 4
        refund = self._create_bare_order(
            session_id=original.session_id.id,
            date_order="2026-09-13 12:00:00",
            shipping_date="2026-09-14",
            is_refund=True,
        )
        line = self._create_line(refund)
        line.write(
            {
                "product_id": original_line.product_id.id,
                "qty": -1,
                "refunded_orderline_id": original_line.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "product_id": line.product_id.id,
                "product_uom_id": line.product_uom_id.id,
                "product_uom_qty": 1,
                "location_id": self.env.ref("stock.stock_location_customers").id,
                "location_dest_id": self.company_data[
                    "default_warehouse"
                ].lot_stock_id.id,
            }
        )

        line._update_total_cost(move)

        self.assertEqual(line.price_cost, 10)
        self.assertEqual(line.total_cost, -30)


@tagged("post_install", "-at_install")
class TestPosOrderLineTotalCost(PosOpenSessionCommon):
    def test_total_cost_survives_a_zero_quantity_refunded_line(self):
        order = self._create_bare_order(shipping_date=fields.Date.today())
        zero_line = self.env["pos.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "qty": 0,
                "price_unit": 0,
                "price_subtotal": 0,
                "price_subtotal_incl": 0,
                "total_cost": 0,
            }
        )
        refund_line = self.env["pos.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "qty": -1,
                "price_unit": 0,
                "price_subtotal": 0,
                "price_subtotal_incl": 0,
                "refunded_orderline_id": zero_line.id,
            }
        )
        refund_line._update_total_cost(self.env["stock.move"])
        self.assertTrue(refund_line.is_total_cost_computed)
