from odoo.tests.common import tagged

from odoo.addons.sale_lazada.tests.common import TestLazadaCommon


@tagged("post_install", "-at_install")
class TestMarketplaceTaxPrices(TestLazadaCommon):
    def test_price_respects_included_and_excluded_taxes(self):
        if "shopee.shop" not in self.env or "amazon.account" not in self.env:
            self.skipTest("Requires the Shopee and Amazon providers")
        excluded = self.env["account.tax"].create(
            {
                "name": "Excluded 10%",
                "amount": 10,
                "price_include_override": "tax_excluded",
            }
        )
        included = self.env["account.tax"].create(
            {
                "name": "Included 20%",
                "amount": 20,
                "price_include_override": "tax_included",
            }
        )
        currency = self.shop.company_id.currency_id
        cases = (
            (excluded, 110, 100),
            (included, 120, 120),
            (excluded | included, 130, 120),
            (excluded | included, -130, -120),
            (excluded.browse(), 42, 42),
            (excluded | included, 0, 0),
        )
        for taxes, total, expected in cases:
            with self.subTest(total=total, taxes=taxes.ids):
                self.assertAlmostEqual(
                    self.shop._get_price_from_tax_included_total(
                        total, taxes, currency
                    ),
                    expected,
                )
                self.assertAlmostEqual(
                    self.env["shopee.shop"]._get_price_from_tax_included_total(
                        total, taxes, currency
                    ),
                    expected,
                )
                self.assertAlmostEqual(
                    self.env["amazon.account"]._get_price_from_order_amounts(
                        total - 5, 5, taxes, currency
                    ),
                    expected,
                )
