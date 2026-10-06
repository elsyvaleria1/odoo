from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleTender(SaleCommon):
    def _lot_with_two_bids(self, qty=10.0):
        buyer_b = self.env["res.partner"].create({"name": "Buyer B"})
        bid_a = self.env["sale.order"].create(
            {
                "partner_id": self.partner.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
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
        return bid_a, bid_b

    def test_inviting_a_buyer_opens_a_sale_tender(self):
        bid_a, bid_b = self._lot_with_two_bids()

        tender = bid_a.tender_id
        self.assertTrue(tender.name.startswith("STD"))
        self.assertEqual(tender.order_ids, bid_a | bid_b)
        self.assertEqual(bid_b.partner_id.name, "Buyer B")
        self.assertEqual(bid_b.line_ids.product_qty, 10.0)

    def test_the_highest_bid_is_best_when_we_sell(self):
        bid_a, bid_b = self._lot_with_two_bids()

        best = bid_a.tender_id._get_best_lines()

        self.assertEqual(best["best_total"], bid_b.line_ids.ids)
        self.assertTrue(bid_b.line_ids.is_best_total)
        self.assertFalse(bid_a.line_ids.is_best_total)

    def test_awarding_the_best_bid_rejects_the_other(self):
        bid_a, bid_b = self._lot_with_two_bids()
        bid_b.line_ids.action_award_line()

        bid_a.tender_id.action_award()

        self.assertRecordValues(
            bid_a | bid_b,
            [
                {"state": "cancel", "outcome": "rejected"},
                {"state": "done", "outcome": "won"},
            ],
        )
        self.assertEqual(bid_a.tender_id.state, "awarded")

    def test_a_lot_can_be_split_between_buyers(self):
        bid_a, bid_b = self._lot_with_two_bids()
        bid_a.line_ids.qty_awarded = 3.0
        bid_b.line_ids.qty_awarded = 7.0

        bid_a.tender_id.action_award()

        self.assertEqual(bid_a.line_ids.product_qty, 3.0)
        self.assertEqual(bid_b.line_ids.product_qty, 7.0)
        self.assertEqual(set((bid_a | bid_b).mapped("state")), {"done"})

    def test_confirming_one_bid_offers_to_reject_the_others(self):
        bid_a, bid_b = self._lot_with_two_bids()

        action = bid_b.action_confirm()
        warning = Form(
            self.env[action["res_model"]].with_context(**action["context"])
        ).save()
        warning.action_reject_rivals()

        self.assertEqual(bid_b.state, "done")
        self.assertEqual(bid_a.outcome, "rejected")

    def test_a_tender_is_awarded_only_with_an_award(self):
        bid_a, _bid_b = self._lot_with_two_bids()

        with self.assertRaisesRegex(UserError, "Award at least one line"):
            bid_a.tender_id.action_award()

    def test_buyers_are_invited_to_the_tender_needs(self):
        tender = self.env["sale.tender"].create(
            {
                "line_ids": [
                    Command.create({"product_id": self.product.id, "product_qty": 3.0})
                ]
            }
        )
        buyer = self.env["res.partner"].create({"name": "Buyer N"})
        action = tender.action_invite()
        wizard = Form(self.env[action["res_model"]].with_context(**action["context"]))
        wizard.partner_ids = buyer
        wizard.save().action_invite()

        self.assertEqual(tender.order_ids.partner_id, buyer)
        self.assertEqual(tender.order_ids.line_ids.product_qty, 3.0)
        self.assertEqual(tender.line_ids.offer_count, 1)
