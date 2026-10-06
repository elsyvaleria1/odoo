from odoo import Command
from odoo.tests import tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleAgreementCompetition(SaleCommon):
    def test_an_agreed_price_is_measured_against_the_market(self):
        rival = self.env["res.partner"].create(
            {"name": "Rival Seeds", "is_competitor": True, "is_company": True}
        )
        self.env["competitor.offer"].create(
            {
                "competitor_id": rival.id,
                "partner_id": self.partner.id,
                "direction": "sale",
                "line_ids": [
                    Command.create({"product_id": self.product.id, "price_unit": 8.0})
                ],
            }
        )
        agreement = self.env["sale.agreement"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 100.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )

        self.assertRecordValues(
            agreement.line_ids,
            [{"market_price": 8.0, "market_scope": "partner", "price_gap": 25.0}],
        )
