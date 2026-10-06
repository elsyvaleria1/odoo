from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseAgreementCompetition(TransactionCase):
    def test_a_rival_buyer_paying_more_puts_the_agreement_below_market(self):
        grower = self.env["res.partner"].create({"name": "Grower"})
        rival = self.env["res.partner"].create(
            {"name": "Rival Buyer", "is_competitor": True, "is_company": True}
        )
        product = self.env["product.product"].create(
            {"name": "Avocado", "purchase_ok": True}
        )
        self.env["competitor.offer"].create(
            {
                "competitor_id": rival.id,
                "partner_id": grower.id,
                "direction": "purchase",
                "line_ids": [
                    Command.create({"product_id": product.id, "price_unit": 12.0})
                ],
            }
        )
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": grower.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_qty": 100.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )

        self.assertEqual(agreement.line_ids.market_price, 12.0)
        self.assertAlmostEqual(agreement.line_ids.price_gap, -100.0 / 6)
