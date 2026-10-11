from datetime import date

from odoo.tests import tagged
from odoo.tools import frozendict

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

    def test_balanced_decimal_amounts_do_not_generate_a_counterpart(self):
        class ExportRecord(frozendict):
            # Keep the three lines in export order when the importer deduplicates them.
            def __hash__(self):
                return int(self["DOCORDER"])

        account = self.company_data["default_account_expense"]
        journal = self.company_data["default_journal_misc"]
        journal.default_account_id = account
        records = [
            ExportRecord(
                DOCNUMBER="1",
                DBKCODE="MISC",
                DBKTYPE="4",
                BOOKYEAR="1",
                PERIOD="1",
                DATEDOC=date(2026, 1, 15),
                DATE=date(2026, 1, 15),
                ACCOUNTGL="WB",
                DOCORDER=str(order),
                AMOUNTEUR=amount,
                CURRAMOUNT=0.0,
                VATIMPUT="",
                COMMENT="Balanced Winbooks fixture",
            )
            for order, amount in enumerate((0.1, 0.2, -0.3), start=1)
        ]
        _, moves = self.wizard._import_move(
            records,
            pdffiles={},
            account_data={"WB": account.id},
            account_central={},
            journal_data={"MISC": journal.id},
            partner_data={},
            vatcode_data={},
            param_data={
                "openyears": [1],
                "period_date": {
                    1: [date(2025, 1, 1), date(2026, 1, 1), date(2027, 1, 1)]
                },
            },
        )
        self.assertEqual(len(moves), 1)
        self.assertEqual(len(moves.line_ids), 3)
        self.assertEqual(moves.line_ids.mapped("winbooks_line_id"), ["1", "2", "3"])

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
