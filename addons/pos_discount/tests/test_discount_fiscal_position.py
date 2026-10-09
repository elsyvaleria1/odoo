from odoo import Command
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosDiscountFiscalPosition(TestPoSCommon):
    def test_a_global_discount_keeps_the_taxes_the_till_mapped(self):
        self.config = self.basic_config
        discount_product = self.env["product.product"].create(
            {"name": "Global discount", "type": "service", "taxes_id": False}
        )
        self.config.write(
            {
                "module_pos_discount": True,
                "discount_product_id": discount_product.id,
            }
        )
        fiscal_position = self.env["account.fiscal.position"].create(
            {"name": "Maps twice"}
        )
        sold_tax = self.env["account.tax"].create({"name": "Sold 10%", "amount": 10})
        mapped_tax = self.env["account.tax"].create(
            {
                "name": "Mapped 20%",
                "amount": 20,
                "fiscal_position_ids": [Command.link(fiscal_position.id)],
                "original_tax_ids": [Command.link(sold_tax.id)],
            }
        )
        self.env["account.tax"].create(
            {
                "name": "Remapped 30%",
                "amount": 30,
                "fiscal_position_ids": [Command.link(fiscal_position.id)],
                "original_tax_ids": [Command.link(mapped_tax.id)],
            }
        )
        product = self.create_product(
            "Discounted", self.categ_basic, 100, tax_ids=sold_tax.ids
        )
        self._start_pos_session(self.cash_pm1, 0)
        data = self.create_ui_order_data(
            [
                {
                    "product": product,
                    "quantity": 1,
                    "tax_ids": [Command.set(sold_tax.ids)],
                },
                {
                    "product": discount_product,
                    "quantity": 1,
                    "price_unit": -10,
                    "tax_ids": [Command.set(mapped_tax.ids)],
                },
            ],
            pos_order_ui_args={"fiscal_position_id": fiscal_position.id},
            payments=[(self.cash_pm1, 108)],
        )

        result = self.env["pos.order"].sync_from_ui([data])
        order = self.env["pos.order"].browse(result["pos.order"][0]["id"])

        discount_line = order.lines.filtered(
            lambda line: line.product_id == discount_product
        )
        self.assertEqual(discount_line.tax_ids_after_fiscal_position, mapped_tax)
        self.assertAlmostEqual(
            discount_line.price_subtotal_incl,
            -12,
            msg="-13 means the server mapped the till's mapped tax a second time",
        )
        self.assertAlmostEqual(order.amount_total, 108)
        self.assertEqual(order.state, "paid")
