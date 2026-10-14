from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosTaxPolicy(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.product = cls.create_product(
            "Taxed in the catalog",
            cls.categ_basic,
            100.0,
            tax_ids=cls.taxes["tax7"].ids,
        )
        (cls.config.journal_id | cls.config.invoice_journal_id).tax_policy = "forbidden"

    def _untaxed_line(self, quantity):
        amount = 100.0 * quantity
        return {
            "product": self.product,
            "quantity": quantity,
            "tax_ids": [(6, 0, [])],
            "price_subtotal": amount,
            "price_subtotal_incl": amount,
        }

    def _sync(self, order_data):
        synced = self.env["pos.order"].sync_from_ui([order_data])["pos.order"]
        return self.env["pos.order"].browse(synced[0]["id"])

    def test_the_journals_of_a_point_of_sale_must_agree(self):
        other_journal = self.config.invoice_journal_id.copy({"tax_policy": "optional"})
        with self.assertRaises(ValidationError):
            self.config.invoice_journal_id = other_journal

    def test_no_session_opens_while_the_journals_disagree(self):
        self.config.invoice_journal_id.tax_policy = "optional"
        with self.assertRaises(ValidationError):
            self.config.open_ui()

    def test_products_load_without_taxes(self):
        rows = self.env["product.template"]._load_pos_data_read(
            self.product.product_tmpl_id, self.config
        )
        self.assertEqual(rows[0]["taxes_id"], [])

    def test_the_product_info_shows_no_tax(self):
        info = self.product.product_tmpl_id._get_pos_price_info(
            100.0, 1, self.config, self.product
        )
        self.assertFalse(info["tax_details"])

    def test_an_untaxed_order_is_invoiced_and_posted(self):
        self.open_new_session()
        order_data = self.create_ui_order_data(
            [self._untaxed_line(2)], customer=self.customer, is_invoiced=True
        )
        order = self._sync(order_data)
        self.assertFalse(order.lines.tax_ids)
        self.assertEqual(order.account_move.state, "posted")
        self.assertFalse(order.account_move.invoice_line_ids.tax_ids)
        self.assertEqual(order.account_move.amount_total, 200.0)

    def test_a_taxed_line_is_a_pricing_breach(self):
        self.open_new_session()
        order_data = self.create_ui_order_data([(self.product, 1)])
        line = self._sync(order_data).lines
        self.assertTrue(line.tax_ids)
        self.assertFalse(line._has_allowed_taxes())
