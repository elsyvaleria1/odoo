from odoo.tests import tagged

from .common import BaseTaxCommon


@tagged("post_install", "-at_install")
class TestTaxMultiCurrency(BaseTaxCommon):
    def _foreign_currency(self):
        foreign = self.env.ref("base.EUR")
        if foreign == self.currency:
            foreign = self.env.ref("base.USD")
        return foreign

    def test_tax_amount_currency_diverges_from_company_currency(self):
        tax = self._tax(21.0)
        Tax = self.env["account.tax"]
        foreign = self._foreign_currency()

        base_line = self._base_line(tax, 100.0, currency_id=foreign, rate=2.0)
        Tax._add_tax_details_in_base_line(base_line, self.company)
        Tax._round_base_lines_tax_details([base_line], self.company)

        totals = Tax._get_tax_totals_summary([base_line], foreign, self.company)

        self.assertAlmostEqual(totals["tax_amount_currency"], 21.0, places=2)
        self.assertAlmostEqual(totals["tax_amount"], 10.5, places=2)
        self.assertAlmostEqual(totals["base_amount_currency"], 100.0, places=2)
        self.assertAlmostEqual(totals["base_amount"], 50.0, places=2)

    def test_rate_of_one_keeps_both_fields_equal(self):
        tax = self._tax(21.0)
        Tax = self.env["account.tax"]
        foreign = self._foreign_currency()

        base_line = self._base_line(tax, 100.0, currency_id=foreign, rate=1.0)
        Tax._add_tax_details_in_base_line(base_line, self.company)
        Tax._round_base_lines_tax_details([base_line], self.company)

        totals = Tax._get_tax_totals_summary([base_line], foreign, self.company)
        self.assertAlmostEqual(
            totals["tax_amount_currency"], totals["tax_amount"], places=2
        )
