from datetime import timedelta

from odoo import Command, fields
from odoo.tests import Form, tagged

from odoo.addons.sale.tests.common import SaleCommon


@tagged("post_install", "-at_install")
class TestSaleCompetition(SaleCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product.standard_price = 5.0
        cls.rival = cls.env["res.partner"].create(
            {"name": "Rival Seeds", "is_competitor": True, "is_company": True}
        )
        cls.other_customer = cls.env["res.partner"].create({"name": "Elsewhere"})
        cls.config = cls.env.company.sale_config_id
        cls.config.write(
            {
                "competition_min_margin": 0.0,
                "competition_undercut": 0.0,
                "competition_leader_gap": 5.0,
            }
        )

    def _quote(self, price=10.0, qty=10.0, partner=None):
        return self.env["sale.order"].create(
            {
                "partner_id": (partner or self.partner).id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": qty,
                            "price_unit": price,
                        }
                    )
                ],
            }
        )

    def _offer(self, price, partner=None, **values):
        line_values = values.pop("line", {})
        return self.env["competitor.offer"].create(
            {
                "competitor_id": self.rival.id,
                "partner_id": (partner or self.partner).id,
                "direction": "sale",
                **values,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 10.0,
                            "price_unit": price,
                            **line_values,
                        }
                    )
                ],
            }
        )

    def test_a_rival_offer_to_the_customer_is_its_market_price(self):
        self._offer(8.0)
        line = self._quote(10.0).line_ids

        self.assertRecordValues(
            line,
            [
                {
                    "market_price": 8.0,
                    "market_scope": "partner",
                    "price_gap": 25.0,
                    "limit_price": 5.0,
                    "recommended_price": 8.0,
                    "market_position": "behind",
                }
            ],
        )
        self.assertEqual(line.order_id.market_position, "behind")

    def test_the_customer_own_offers_outrank_the_market(self):
        self._offer(6.0, partner=self.other_customer)
        self._offer(8.0)

        line = self._quote(10.0).line_ids

        self.assertEqual(line.market_price, 8.0)
        self.assertEqual(line.market_scope, "partner")

    def test_without_own_offers_the_whole_market_answers(self):
        self._offer(6.0, partner=self.other_customer)

        line = self._quote(10.0).line_ids

        self.assertEqual(line.market_price, 6.0)
        self.assertEqual(line.market_scope, "market")

    def test_positions_follow_the_gap_and_the_floor(self):
        self._offer(8.0)

        self.assertEqual(self._quote(7.0).line_ids.market_position, "leader")
        self.assertEqual(self._quote(7.9).line_ids.market_position, "competitive")
        self.product.categ_id.sale_min_margin = 100.0
        line = self._quote(10.0).line_ids
        self.assertEqual(line.limit_price, 10.0)
        self.assertEqual(line.recommended_price, 10.0)
        self.assertEqual(line.market_position, "cannot_match")

    def test_the_undercut_lowers_the_recommended_price(self):
        self.config.competition_undercut = 10.0
        self._offer(8.0)

        self.assertAlmostEqual(self._quote(10.0).line_ids.recommended_price, 7.2)

    def test_stale_inferior_and_expired_offers_are_not_the_market(self):
        today = fields.Date.context_today(self.env.user)
        self._offer(7.0, date=today - timedelta(days=120))
        self._offer(6.0, line={"equivalence": "inferior"})
        self._offer(
            5.0,
            date=today - timedelta(days=10),
            date_valid=today - timedelta(days=1),
        )

        line = self._quote(10.0).line_ids

        self.assertFalse(line.market_position)
        self.assertEqual(line.market_price, 0.0)
        self.assertEqual(line.limit_price, 5.0)

    def test_market_price_converts_to_the_line_unit(self):
        dozen = self.env.ref("base.product_uom_dozen")
        self._offer(96.0, line={"product_uom_id": dozen.id})

        line = self._quote(10.0).line_ids

        self.assertAlmostEqual(line.market_price, 8.0)

    def test_freight_left_to_the_customer_counts_when_the_company_asks(self):
        offer = self._offer(8.0, freight_per_unit=1.0)
        self.assertEqual(offer.line_ids.price_comparable, 8.0)

        self.env.company.trade_config_id.competition_freight_adjusted = True
        offer.line_ids._compute_price_comparable()

        self.assertEqual(offer.line_ids.price_comparable, 9.0)

    def test_credit_is_discounted_when_the_company_asks(self):
        self.env.company.trade_config_id.competition_financing_rate = 36.5
        offer = self._offer(10.1, credit_days=10)

        self.assertAlmostEqual(offer.line_ids.price_comparable, 10.0)

    def test_losing_records_the_winner_and_their_offer(self):
        quote = self._quote(10.0)
        self._offer(8.0)
        wizard = Form(
            self.env["wizard.sale.order.mark.lost"].with_context(active_ids=quote.ids)
        )
        wizard.lost_to_id = self.rival
        wizard.winning_amount = 80.0
        wizard.save().action_close()

        self.assertRecordValues(
            quote,
            [
                {
                    "outcome": "lost",
                    "lost_to_id": self.rival.id,
                    "price_gap_at_close": 25.0,
                }
            ],
        )
        winner = quote.competitor_offer_ids.filtered("is_winner")
        self.assertEqual(winner.competitor_id, self.rival)
        self.assertEqual(winner.line_ids.price_unit, 8.0)
        self.assertEqual(quote.competitor_ids, self.rival)

    def test_confirming_records_the_gap_at_close(self):
        self._offer(8.0)
        quote = self._quote(7.2)

        quote.action_confirm()

        self.assertAlmostEqual(quote.price_gap_at_close, -10.0)

    def test_a_cheaper_rival_offer_alerts_the_open_quotation(self):
        quote = self._quote(10.0)
        other_quote = self._quote(10.0, partner=self.other_customer)

        self._offer(8.0)
        self._offer(12.0, partner=self.other_customer)

        self.assertEqual(len(quote.activity_ids), 1)
        self.assertIn(self.rival.name, quote.activity_ids.note)
        self.assertFalse(other_quote.activity_ids)

    def test_recording_an_offer_starts_from_the_quotation(self):
        quote = self._quote(10.0)
        action = quote.action_record_competitor_offer()

        form = Form(self.env[action["res_model"]].with_context(**action["context"]))
        form.competitor_id = self.rival
        with form.line_ids.edit(0) as line:
            line.price_unit = 9.0
        offer = form.save()

        self.assertEqual(offer.sale_order_id, quote)
        self.assertEqual(offer.line_ids.product_qty, 10.0)
        self.assertEqual(quote.competitor_offer_count, 1)
        self.assertEqual(quote.line_ids.market_price, 9.0)

    def test_market_prices_group_by_competitor_and_month(self):
        self._offer(8.0)
        self._offer(6.0, partner=self.other_customer)

        groups = self.env["competitor.offer.line"]._read_group(
            [("direction", "=", "sale"), ("product_id", "=", self.product.id)],
            ["competitor_id", "date:month"],
            ["price_comparable:avg"],
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], self.rival)
        self.assertEqual(groups[0][2], 7.0)

    def test_the_competitor_keeps_our_record_against_it(self):
        self._offer(8.0)
        won = self._quote(7.2)
        self._offer(8.0, sale_order_id=won.id)
        won.action_confirm()
        lost = self._quote(10.0)
        wizard = Form(
            self.env["wizard.sale.order.mark.lost"].with_context(active_ids=lost.ids)
        )
        wizard.lost_to_id = self.rival
        wizard.save().action_close()
        still_open = self._quote(9.0)
        self._offer(8.0, sale_order_id=still_open.id)

        self.assertRecordValues(
            self.rival,
            [
                {
                    "competitor_deal_count": 2,
                    "competitor_won_count": 1,
                    "competitor_lost_count": 1,
                    "competitor_win_rate": 50.0,
                }
            ],
        )
        self.assertAlmostEqual(
            self.rival.competitor_price_gap,
            (won.price_gap_at_close + lost.price_gap_at_close) / 2,
        )

    def test_the_price_history_shows_the_competitors(self):
        self._offer(8.0)
        self._offer(9.0)
        self._offer(6.0, partner=self.other_customer)
        quote = self._quote(10.0)

        wizard = self.env["wizard.sale.order.line.view.price.history"].create(
            {
                "line_id": quote.line_ids.id,
                "product_id": self.product.id,
                "partner_id": self.partner.id,
            }
        )

        self.assertRecordValues(
            wizard,
            [
                {
                    "competitor_best_price": 6.0,
                    "competitor_avg_price": 23.0 / 3,
                    "competitor_partner_price": 8.0,
                    "competitor_offer_count": 3,
                }
            ],
        )

    def test_the_customer_industry_answers_before_the_market(self):
        growers, packers = self.env["res.partner.industry"].create(
            [{"name": "Growers"}, {"name": "Packers"}]
        )
        self.partner.industry_ids = growers
        self.other_customer.industry_ids = growers
        packer = self.env["res.partner"].create(
            {"name": "Packing House", "industry_ids": [(6, 0, packers.ids)]}
        )
        self._offer(7.0, partner=self.other_customer)
        self._offer(5.0, partner=packer)

        line = self._quote(10.0).line_ids

        self.assertEqual(line.market_scope, "segment")
        self.assertEqual(line.market_price, 7.0)

    def test_the_quotation_ranks_among_the_offers_it_meets(self):
        quote = self._quote(10.0)
        self._offer(8.0, sale_order_id=quote.id)
        self._offer(12.0, sale_order_id=quote.id)

        self.assertRecordValues(quote, [{"market_rank": 2, "market_offer_count": 2}])
        action = quote.action_compare_competitor_offers()
        self.assertEqual(
            self.env["competitor.offer.line"].search(action["domain"]).offer_id,
            quote.competitor_offer_ids,
        )
