from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestTaxTagImport(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wizard = cls.env["wizard.account.move.import.winbooks"].create(
            {"zip_file": b"dGVzdA=="}
        )

    def test_empty_codes_return_empty_tags(self):
        for codes in (None, "", "unsigned"):
            tags = self.wizard._get_or_create_tax_tags(codes, {})
            self.assertEqual(tags._name, "account.account.tag")
            self.assertFalse(tags)

    def test_create_cache_and_reuse_tags(self):
        cache = {}
        tags = self.wizard._get_or_create_tax_tags("+Winbooks A-Winbooks B", cache)
        self.assertEqual(tags.mapped("name"), ["Winbooks A", "Winbooks B"])
        self.assertEqual(set(cache), {"Winbooks A", "Winbooks B"})
        self.assertEqual(cache["Winbooks A"], tags[:1])
        self.assertEqual(cache["Winbooks B"], tags[1:])
        self.assertEqual(set(tags.mapped("applicability")), {"taxes"})
        self.assertEqual(
            tags.country_id,
            self.env.company.tax_config_id.account_fiscal_country_id,
        )
        with self.assertQueryCount(0):
            self.assertEqual(
                self.wizard._get_or_create_tax_tags("+Winbooks A-Winbooks B", cache),
                tags,
            )
        self.assertEqual(
            self.wizard._get_or_create_tax_tags("+Winbooks A-Winbooks B", {}), tags
        )

    def test_import_repartition_links_and_reuse_tax(self):
        records = [
            {
                "TREELEVEL": "01",
                "TREELIB1": "Winbooks tax fixture",
                "USRCODE1": "yes",
                "CODE": "2fixture",
                "RATE": 21.0,
                "TAXFORM": "BAL",
                "BASE_CN": "",
                "TAX_CN": "+Winbooks refund",
                "BASE_INV": "+Winbooks base",
                "TAX_INV": "+Winbooks tax",
            }
        ]
        mapping, taxes = self.wizard._import_vat(records, {})
        self.assertEqual(mapping, {"2fixture": taxes.id})
        self.assertEqual(taxes.amount, 21)
        self.assertEqual(
            taxes.invoice_repartition_line_ids.tag_ids.mapped("name"),
            ["Winbooks base", "Winbooks tax"],
        )
        self.assertEqual(
            taxes.refund_repartition_line_ids.tag_ids.mapped("name"),
            ["Winbooks refund"],
        )
        repeated_mapping, new_taxes = self.wizard._import_vat(records, {})
        self.assertEqual(repeated_mapping, mapping)
        self.assertFalse(new_taxes)
