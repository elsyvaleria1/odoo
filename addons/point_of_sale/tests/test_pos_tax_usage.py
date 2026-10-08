import odoo
from odoo.exceptions import ValidationError

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestPosTaxUsage(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def test_a_tax_on_an_open_session_order_cannot_be_deleted(self):
        self._start_pos_session(self.cash_pm1, 0)
        tax = self.env["account.tax"].create(
            {
                "name": "AuditTaxR4",
                "amount": 10.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
            }
        )
        product = self.create_product(
            "AuditTaxProdR4", self.categ_basic, 100, 50, tax_ids=tax.ids
        )
        self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(product, 1)],
                    "payments": [(self.cash_pm1, 110)],
                    "uuid": "audit-r4-0001",
                },
            ]
        )
        tax.invalidate_model(fnames=["is_used"])
        self.assertTrue(
            tax.is_used,
            "a tax carried by an open-session POS order must count as used, so "
            "that it cannot be deleted out from under the closing entry",
        )
        with self.assertRaises(ValidationError):
            tax.unlink()
        self.assertTrue(tax.exists())

        tax.active = False
        self.assertFalse(tax.active)

    def test_a_tax_on_a_synced_order_line_is_used(self):
        self.open_new_session()
        product = self.create_product(
            "TaxUsedProd", self.categ_basic, 100, tax_ids=self.taxes["tax7"].ids
        )
        order = self.create_ui_order_data([(product, 1)])
        self.env["pos.order"].sync_from_ui([order])

        self.assertTrue(
            self.taxes["tax7"].is_used,
            "a tax carried by a pos.order.line must count as used",
        )
