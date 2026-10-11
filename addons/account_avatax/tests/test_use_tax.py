from odoo import Command
from odoo.tests.common import tagged

from .common import TestAccountAvataxCommon, TestAvataxCommon


@tagged("-at_install", "post_install")
class TestAccountAvalaraUseTaxVendorManagement(TestAvataxCommon):

    @classmethod
    def setUpClass(cls):
        res = super().setUpClass()
        cls.config = cls.env["res.config.settings"].create({})
        return res

    def test_vendor_identifier_mapping(self):
        Partner = self.env["res.partner"]
        partner = Partner.search([], limit=1)
        partner_via_code = Partner.search(
            [("avatax_unique_code", "=", partner.avatax_unique_code)], limit=1
        )
        self.assertEqual(
            partner, partner_via_code, "Couldn't find partner via unique avatax code"
        )


@tagged("-at_install", "post_install")
class TestAccountAvalaraUseTaxProductManagement(TestAccountAvataxCommon):

    def test_item_code(self):
        self.env.company.avalara_use_upc = False
        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            invoice = self._create_invoice(post=False)
            invoice.button_external_tax_calculation()
        self.assertEqual(
            capture.val["json"]["createTransactionModel"]["lines"][0]["itemCode"],
            "PROD1",
        )

        self.env.company.avalara_use_upc = True
        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            invoice = self._create_invoice(post=False)
            invoice.button_external_tax_calculation()
        self.assertEqual(
            capture.val["json"]["createTransactionModel"]["lines"][0]["itemCode"],
            "UPC:123456789",
        )

    def test_item_code_is_not_more_than_50_characters(self):
        product = self.env["product.product"].create(
            {
                "name": "Product",
                "default_code": 100 * "A",
                "barcode": 100 * "1",
                "list_price": 15.00,
                "standard_price": 15.00,
                "supplier_taxes_id": None,
                "avatax_category_id": self.env.ref("account_avatax.DC010000").id,
            }
        )

        self.env.company.avalara_use_upc = False
        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            invoice = self._create_invoice(
                invoice_line_ids=[
                    Command.create({"product_id": product.id, "price_unit": 100})
                ]
            )
            invoice.button_external_tax_calculation()
        self.assertEqual(
            len(capture.val["json"]["createTransactionModel"]["lines"][0]["itemCode"]),
            50,
        )

        self.env.company.avalara_use_upc = True
        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            invoice = self._create_invoice(
                invoice_line_ids=[
                    Command.create({"product_id": product.id, "price_unit": 100})
                ]
            )
            invoice.button_external_tax_calculation()
        self.assertEqual(
            len(capture.val["json"]["createTransactionModel"]["lines"][0]["itemCode"]),
            50,
        )

    def test_item_description(self):
        with self._capture_request(
            return_value={"lines": [], "summary": []}
        ) as capture:
            invoice = self._create_invoice(post=False)
            invoice.button_external_tax_calculation()
        line_description = capture.val["json"]["createTransactionModel"]["lines"][0][
            "description"
        ]
        self.assertEqual(
            invoice.invoice_line_ids.product_id.display_name, line_description
        )
