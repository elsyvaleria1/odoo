from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseCompetition(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Grower"})
        cls.other_vendor = cls.env["res.partner"].create({"name": "Elsewhere"})
        cls.rival = cls.env["res.partner"].create(
            {"name": "Rival Buyer", "is_competitor": True, "is_company": True}
        )
        cls.category = cls.env["product.category"].create({"name": "Fruit"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Avocado",
                "categ_id": cls.category.id,
                "type": "consu",
                "purchase_ok": True,
                "list_price": 20.0,
                "supplier_taxes_id": [Command.clear()],
            }
        )
        cls.config = cls.env.company.purchase_config_id
        cls.config.write(
            {
                "competition_min_margin": 0.0,
                "competition_overbid": 0.0,
                "competition_leader_gap": 5.0,
            }
        )

    def _rfq(self, price=10.0, vendor=None):
        return self.env["purchase.order"].create(
            {
                "partner_id": (vendor or self.vendor).id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 10.0,
                            "price_unit": price,
                        }
                    )
                ],
            }
        )

    def _offer(self, price, vendor=None, **values):
        return self.env["competitor.offer"].create(
            {
                "competitor_id": self.rival.id,
                "partner_id": (vendor or self.vendor).id,
                "direction": "purchase",
                **values,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 10.0,
                            "price_unit": price,
                        }
                    )
                ],
            }
        )

    def test_a_rival_buyer_paying_more_puts_us_behind_the_market(self):
        self._offer(12.0)

        line = self._rfq(10.0).line_ids

        self.assertRecordValues(
            line,
            [
                {
                    "market_price": 12.0,
                    "market_scope": "partner",
                    "limit_price": 20.0,
                    "recommended_price": 12.0,
                    "market_position": "behind",
                }
            ],
        )
        self.assertAlmostEqual(line.price_gap, -100.0 / 6)

    def test_the_highest_rival_price_is_the_market(self):
        self._offer(12.0, vendor=self.other_vendor)
        self._offer(14.0, vendor=self.other_vendor)

        line = self._rfq(10.0).line_ids

        self.assertEqual(line.market_price, 14.0)
        self.assertEqual(line.market_scope, "market")

    def test_the_vendor_own_offers_outrank_the_market(self):
        self._offer(14.0, vendor=self.other_vendor)
        self._offer(12.0)

        self.assertEqual(self._rfq(10.0).line_ids.market_price, 12.0)

    def test_positions_follow_the_gap_and_the_ceiling(self):
        self._offer(12.0)

        self.assertEqual(self._rfq(13.0).line_ids.market_position, "leader")
        self.assertEqual(self._rfq(12.3).line_ids.market_position, "competitive")
        self.category.purchase_min_margin = 100.0
        line = self._rfq(9.0).line_ids
        self.assertEqual(line.limit_price, 10.0)
        self.assertEqual(line.recommended_price, 10.0)
        self.assertEqual(line.market_position, "cannot_match")

    def test_the_overbid_raises_the_recommended_price(self):
        self.config.competition_overbid = 10.0
        self._offer(12.0)

        self.assertAlmostEqual(self._rfq(10.0).line_ids.recommended_price, 13.2)

    def test_without_a_resale_price_there_is_no_ceiling(self):
        self.product.list_price = 0.0
        self.category.purchase_min_margin = 100.0
        self._offer(12.0)

        line = self._rfq(9.0).line_ids

        self.assertEqual(line.limit_price, 0.0)
        self.assertEqual(line.market_position, "behind")

    def test_freight_left_to_the_grower_lowers_a_rival_price(self):
        self.env.company.trade_config_id.competition_freight_adjusted = True

        offer = self._offer(12.0, freight_per_unit=1.0)

        self.assertEqual(offer.line_ids.price_comparable, 11.0)

    def test_losing_records_the_rival_buyer_and_their_offer(self):
        rfq = self._rfq(10.0)
        self._offer(12.0)
        wizard = Form(
            self.env["wizard.purchase.order.mark.lost"].with_context(active_ids=rfq.ids)
        )
        wizard.lost_to_id = self.rival
        wizard.winning_amount = 125.0

        wizard.save().action_close()

        self.assertRecordValues(rfq, [{"outcome": "lost", "lost_to_id": self.rival.id}])
        self.assertAlmostEqual(rfq.price_gap_at_close, -100.0 / 6)
        winner = rfq.competitor_offer_ids.filtered("is_winner")
        self.assertEqual(winner.direction, "purchase")
        self.assertEqual(winner.line_ids.price_unit, 12.5)
        self.assertEqual(rfq.competitor_ids, self.rival)

    def test_a_higher_rival_offer_alerts_the_open_request(self):
        outbid = self._rfq(10.0)
        safe = self._rfq(10.0, vendor=self.other_vendor)

        self._offer(12.0)
        self._offer(8.0, vendor=self.other_vendor)

        self.assertEqual(len(outbid.activity_ids), 1)
        self.assertIn(self.rival.name, outbid.activity_ids.note)
        self.assertFalse(safe.activity_ids)

    def test_recording_an_offer_starts_from_the_request(self):
        rfq = self._rfq(10.0)
        action = rfq.action_record_competitor_offer()

        form = Form(self.env[action["res_model"]].with_context(**action["context"]))
        form.competitor_id = self.rival
        with form.line_ids.edit(0) as line:
            line.price_unit = 11.0
        offer = form.save()

        self.assertEqual(offer.purchase_order_id, rfq)
        self.assertEqual(offer.direction, "purchase")
        self.assertEqual(rfq.competitor_offer_count, 1)
        self.assertEqual(rfq.line_ids.market_price, 11.0)

    def test_the_price_history_shows_the_highest_rival_price(self):
        self._offer(12.0)
        self._offer(14.0, vendor=self.other_vendor)
        rfq = self._rfq(10.0)

        wizard = self.env["wizard.purchase.order.line.view.price.history"].create(
            {
                "line_id": rfq.line_ids.id,
                "product_id": self.product.id,
                "partner_id": self.vendor.id,
            }
        )

        self.assertRecordValues(
            wizard,
            [
                {
                    "competitor_best_price": 14.0,
                    "competitor_partner_price": 12.0,
                    "competitor_offer_count": 2,
                }
            ],
        )

    def test_a_rival_buyer_paying_more_ranks_above_our_request(self):
        rfq = self._rfq(10.0)
        self._offer(12.0, purchase_order_id=rfq.id)
        self._offer(9.0, purchase_order_id=rfq.id)

        self.assertRecordValues(rfq, [{"market_rank": 2, "market_offer_count": 2}])
