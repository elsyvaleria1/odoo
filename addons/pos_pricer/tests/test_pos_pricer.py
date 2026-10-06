from odoo.tests import Form, TransactionCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.product.tests.common import ProductCommon


@tagged("post_install", "-at_install")
class TestPosPricer(ProductCommon, TransactionCase):
    def test_pos_pricer_sales_pricelist(self):
        """
        Test that the pricer sales pricelist is correctly applied to products
        """
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "compute_price": "percentage",
                "applied_on": "3_global",
                "percent_price": 10,
            }
        )
        ProductForm = Form(self.env["product.product"])
        ProductForm.name = "Demo Product"
        ProductForm.lst_price = 100
        ProductForm.pricer_sale_pricelist_id = self.pricelist
        self.assertEqual(ProductForm.on_sale_price, 90)
        ProductForm.save()
        # After saving, on_sale_price should change if lst_price is modified
        ProductForm.lst_price = 100
        self.assertEqual(ProductForm.on_sale_price, 90)

    def test_pricer_display_compute_price(self):
        """Ensure the compute method sets a default value to avoid crash."""
        product_form = Form(self.env["product.product"])
        product_form.name = "Test Product"
        product = product_form.save()
        display_price = product.pricer_display_price
        self.assertFalse(display_price)


@tagged("post_install", "-at_install")
class TestPosPricerLabelPrice(AccountTestInvoicingCommon):
    """`product.taxes_id` carries every company's default sale tax on purpose, so
    a label price has to be computed from the active company's subset alone.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_company = cls.setup_other_company()["company"]
        cls.both_companies = cls.env.company | cls.other_company
        cls.product = (
            cls.env["product.template"]
            .with_context(allowed_company_ids=cls.env.company.ids)
            .with_company(cls.env.company)
            .create({"name": "Pricer Label", "list_price": 100.0})
            .product_variant_id
        )

    def _expected_label_price(self):
        taxes = self.product.sudo().taxes_id._filter_taxes_by_company(self.env.company)
        self.assertTrue(
            taxes, "control: the active company must have a default sale tax"
        )
        return taxes.compute_all(
            self.product.lst_price,
            product=self.product,
            partner=self.env["res.partner"],
        )["total_included"]

    def test_control_the_product_carries_the_other_companys_tax(self):
        self.assertIn(
            self.other_company,
            self.product.sudo().taxes_id.company_ids,
            "control: without a foreign tax on the record this test proves nothing."
            " sudo() has to come before the read: taxes_id.sudo() elevates a"
            " recordset the account.tax company guard has already filtered.",
        )

    def test_label_price_ignores_other_companies_taxes(self):
        widened = self.product.with_context(allowed_company_ids=self.both_companies.ids)
        self.assertIn(
            self.other_company,
            widened.taxes_id.company_ids,
            "control: with both companies active the account.tax company guard stops"
            " masking the foreign tax",
        )
        self.assertEqual(
            float(widened.compute_prices()),
            self._expected_label_price(),
        )

    def test_label_price_ignores_other_companies_taxes_under_sudo(self):
        expected = self._expected_label_price()
        self.env.invalidate_all()
        self.assertIn(
            self.other_company,
            self.product.sudo().taxes_id.company_ids,
            "control: sudo bypasses the company guard",
        )
        self.assertEqual(float(self.product.sudo().compute_prices()), expected)
