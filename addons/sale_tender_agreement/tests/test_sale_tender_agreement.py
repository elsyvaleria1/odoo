from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleTenderAgreement(SaleCommon):
    def _lot_with_two_bids(self):
        buyer_b = self.env["res.partner"].create({"name": "Buyer B"})
        bid_a = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 10.0,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        action = bid_a.action_invite_counterparties()
        wizard = Form(self.env[action["res_model"]].with_context(**action["context"]))
        wizard.partner_ids = buyer_b
        wizard.save().action_invite()
        bid_b = bid_a.tender_id.order_ids - bid_a
        bid_b.line_ids.price_unit = 12.0
        tender = bid_a.tender_id
        tender.write(
            {
                "award_as": "agreements",
                "date_start": fields.Date.from_string("2027-01-01"),
                "date_end": fields.Date.from_string("2027-06-30"),
            }
        )
        return tender, bid_a, bid_b

    def test_the_best_bid_becomes_an_agreement_with_its_buyer(self):
        tender, bid_a, bid_b = self._lot_with_two_bids()
        bid_b.line_ids.action_award_line()

        tender.action_award()

        agreement = bid_b.awarded_agreement_id
        self.assertEqual(agreement._name, "sale.agreement")
        self.assertRecordValues(
            agreement,
            [
                {
                    "partner_id": bid_b.partner_id.id,
                    "state": "confirmed",
                    "date_end": fields.Date.from_string("2027-06-30"),
                }
            ],
        )
        self.assertRecordValues(
            agreement.line_ids, [{"product_qty": 10.0, "price_unit": 12.0}]
        )
        self.assertRecordValues(
            bid_a | bid_b,
            [
                {"state": "cancel", "outcome": "rejected"},
                {"state": "cancel", "outcome": "won"},
            ],
        )

    def test_orders_released_to_the_buyer_consume_the_agreement(self):
        tender, _bid_a, bid_b = self._lot_with_two_bids()
        bid_b.line_ids.action_award_line()
        tender.action_award()
        agreement = bid_b.awarded_agreement_id

        order_form = Form(self.env["sale.order"])
        order_form.partner_id = bid_b.partner_id
        order_form.agreement_id = agreement
        release = order_form.save()
        release.line_ids.product_qty = 4.0
        release.action_confirm()

        self.assertEqual(agreement.line_ids.qty_ordered, 4.0)
