import logging

from odoo.tests import tagged

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.product_matrix.tests.common import TestMatrixCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestSaleMatrixUi(TestMatrixCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        mail_new_test_user(
            cls.env,
            name="Salesman",
            login="salesman",
            password="salesman",
            groups="sale.group_sale_salesman",
        )

        cls.env["res.partner"].create({"name": "Agrolait"})

        cls.env["res.currency"].search([("name", "!=", "USD")]).with_context(
            force_deactivate=True
        ).action_archive()
        cls.currency = cls.env["res.currency"].search([("name", "=", "USD")])
        cls.currency.action_unarchive()
        cls.env.company.currency_id = cls.currency

    def test_sale_matrix_ui(self):
        self.env.ref("base.group_user").implied_ids += self.env.ref(
            "sale.group_sale_order_template"
        )
        self.env["account.tax"].search([]).write({"active": False})
        tax = self.env["account.tax"].create(
            {
                "name": "15%",
                "amount": 15,
            }
        )
        self.matrix_template.taxes_id = tax
        self.env["product.pricelist"].search([]).write({"active": False})

        self.env["product.pricelist"].search([]).unlink()

        self.matrix_template.product_add_mode = "matrix"

        self.start_tour("/odoo", "sale_matrix_tour", login="salesman")

        self.assertEqual(len(self.matrix_template.product_variant_ids), 8)
        self.assertEqual(
            len(
                self.matrix_template.product_variant_ids.product_template_attribute_value_ids
            ),
            6,
        )
        self.assertEqual(
            len(self.matrix_template.attribute_line_ids.product_template_value_ids), 8
        )
        self.env["sale.order.line"].search(
            [("product_id", "in", self.matrix_template.product_variant_ids.ids)]
        ).order_id.action_confirm()

        self.env.flush_all()
        self.assertEqual(round(self.matrix_template.sales_count, 2), 56.8)
        for variant in self.matrix_template.product_variant_ids:
            self.assertIn(round(variant.sales_count, 2), [5, 9.2])

        self.assertEqual(
            len(
                self.env["sale.order.line"].search(
                    [("product_id", "in", self.matrix_template.product_variant_ids.ids)]
                )
            ),
            len(self.matrix_template.product_variant_ids) * 2,
        )
