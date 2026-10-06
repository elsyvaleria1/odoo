from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.purchase_tender.tests.common import TestPurchaseTenderCommon


@tagged("post_install", "-at_install")
class TestPurchaseTenderAgreement(TestPurchaseTenderCommon):
    def _tender_of_two(self, qty=10.0):
        vendor_b = self.env["res.partner"].create({"name": "Vendor B"})
        po_a = self.env["purchase.order"].create(
            {
                "partner_id": self.res_partner_1.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_qty": qty,
                            "price_unit": 10.0,
                        }
                    )
                ],
            }
        )
        action = po_a.action_invite_counterparties()
        wizard = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        wizard.partner_ids = vendor_b
        wizard.save().action_invite()
        po_b = po_a.tender_id.order_ids - po_a
        po_b.line_ids.price_unit = 8.0
        tender = po_a.tender_id
        tender.write(
            {
                "award_as": "agreements",
                "date_start": fields.Date.from_string("2027-01-01"),
                "date_end": fields.Date.from_string("2027-12-31"),
            }
        )
        return tender, po_a, po_b

    def test_the_award_opens_an_agreement_with_the_winner(self):
        tender, po_a, po_b = self._tender_of_two()
        po_b.line_ids.discount = 25.0
        po_b.line_ids.action_award_line()

        tender.action_award()

        agreement = po_b.awarded_agreement_id
        self.assertRecordValues(
            agreement,
            [
                {
                    "partner_id": po_b.partner_id.id,
                    "state": "confirmed",
                    "commitment": "quantity",
                    "reference": tender.name,
                    "date_start": fields.Date.from_string("2027-01-01"),
                    "date_end": fields.Date.from_string("2027-12-31"),
                }
            ],
        )
        self.assertRecordValues(
            agreement.line_ids,
            [
                {
                    "product_id": self.product_09.id,
                    "product_qty": 10.0,
                    "price_unit": 6.0,
                }
            ],
        )
        self.assertRecordValues(
            po_a | po_b,
            [
                {"state": "cancel", "outcome": "rejected"},
                {"state": "cancel", "outcome": "won"},
            ],
        )
        self.assertEqual(tender.agreement_ids, agreement)
        self.assertEqual(tender.state, "awarded")

    def test_a_split_award_opens_one_agreement_per_winner(self):
        tender, po_a, po_b = self._tender_of_two()
        po_a.line_ids.qty_awarded = 4.0
        po_b.line_ids.qty_awarded = 6.0

        tender.action_award()

        self.assertEqual(len(tender.agreement_ids), 2)
        self.assertEqual(po_a.awarded_agreement_id.line_ids.product_qty, 4.0)
        self.assertEqual(po_b.awarded_agreement_id.line_ids.product_qty, 6.0)
        self.assertEqual((po_a | po_b).mapped("outcome"), ["won", "won"])

    def test_a_value_commitment_commits_the_awarded_total(self):
        tender, _po_a, po_b = self._tender_of_two()
        tender.agreement_commitment = "value"
        po_b.line_ids.action_award_line()

        tender.action_award()

        self.assertEqual(po_b.awarded_agreement_id.amount_committed, 80.0)

    def test_orders_released_from_the_agreement_consume_it(self):
        tender, _po_a, po_b = self._tender_of_two()
        po_b.line_ids.action_award_line()
        tender.action_award()
        agreement = po_b.awarded_agreement_id

        release = Form(
            self.env["purchase.order"].with_context(default_agreement_id=agreement.id)
        ).save()
        release.line_ids.product_qty = 3.0
        release.action_confirm()

        self.assertEqual(agreement.line_ids.qty_ordered, 3.0)
        self.assertEqual(agreement.line_ids.qty_remaining, 7.0)

    def test_an_award_as_orders_still_confirms_the_winner(self):
        tender, _po_a, po_b = self._tender_of_two()
        tender.award_as = "orders"
        po_b.line_ids.action_award_line()

        tender.action_award()

        self.assertEqual(po_b.state, "done")
        self.assertFalse(tender.agreement_ids)

    def test_an_offer_invited_from_a_release_is_not_a_release(self):
        agreement = self.env["purchase.agreement"].create(
            {
                "partner_id": self.res_partner_1.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_09.id,
                            "product_qty": 10.0,
                            "price_unit": 41.0,
                        }
                    )
                ],
            }
        )
        agreement.action_confirm()
        release = Form(
            self.env["purchase.order"].with_context(
                default_agreement_id=agreement.id, default_user_id=False
            )
        ).save()
        release.action_confirm()
        self.assertEqual(release.agreement_id, agreement)

        action = release.action_invite_counterparties()
        wizard = Form(
            self.env["wizard.purchase.order.invite.vendor"].with_context(
                **action["context"]
            )
        )
        wizard.partner_ids = self.res_partner_1
        wizard.copy_products = True
        wizard.save().action_invite()

        offer = release.tender_id.order_ids - release
        self.assertTrue(offer)
        self.assertFalse(offer.agreement_id)
