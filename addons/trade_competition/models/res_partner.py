from collections import defaultdict

from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_competitor = fields.Boolean(
        string="Competitor",
        index=True,
        help="A company competing with us for our customers or our growers.",
    )
    competitor_category_ids = fields.Many2many(
        comodel_name="product.category",
        string="Competes On",
        help="The product categories this competitor offers or buys.",
    )
    competitor_offer_ids = fields.One2many(
        comodel_name="competitor.offer",
        inverse_name="competitor_id",
        string="Offers Seen",
    )
    competitor_offer_count = fields.Integer(
        string="Competitor Offers",
        compute="_compute_competitor_offer_count",
    )

    competitor_deal_count = fields.Integer(
        string="Deals Met",
        compute="_compute_competitor_record",
        help="Our won and lost orders this competitor was part of: its offers "
        "competed with them, or it won them.",
    )
    competitor_won_count = fields.Integer(
        string="Won Against Them",
        compute="_compute_competitor_record",
    )
    competitor_lost_count = fields.Integer(
        string="Lost to Them",
        compute="_compute_competitor_record",
    )
    competitor_win_rate = fields.Float(
        string="Our Win Rate (%)",
        compute="_compute_competitor_record",
        help="The share of the deals met that we won.",
    )
    competitor_price_gap = fields.Float(
        string="Typical Gap at Close (%)",
        compute="_compute_competitor_record",
        help="Our average gap to the market when those deals closed: above zero "
        "we asked more than the market when selling, or offered more when "
        "buying.",
    )

    @api.depends("competitor_offer_ids")
    def _compute_competitor_offer_count(self) -> None:
        counts = dict(
            self.env["competitor.offer"]
            .with_privilege(
                "trade_competition.privilege_count_competitor_offers",
                reason="the offers seen on a partner, counted for any reader of it",
            )
            ._read_group(
                [("competitor_id", "in", self.ids)],
                groupby=["competitor_id"],
                aggregates=["__count"],
            )
        )
        for partner in self:
            partner.competitor_offer_count = counts.get(partner, 0)

    def _compute_competitor_record(self) -> None:
        record = defaultdict(lambda: {"deals": 0, "won": 0, "lost": 0, "gap": 0.0})
        competitors = self.filtered("is_competitor")
        for model in self.env["competitor.offer"]._competition_order_models():
            orders = self.env[model].search(  # noqa: E8507 - one search per trade direction, not per partner
                [
                    ("outcome", "in", ["won", "lost"]),
                    "|",
                    ("competitor_ids", "in", competitors.ids),
                    ("lost_to_id", "in", competitors.ids),
                ]
            )
            for order in orders:
                for competitor in (
                    order.competitor_ids | order.lost_to_id
                ) & competitors:
                    stats = record[competitor]
                    stats["deals"] += 1
                    stats["gap"] += order.price_gap_at_close
                    if order.outcome == "won":
                        stats["won"] += 1
                    elif order.lost_to_id == competitor:
                        stats["lost"] += 1
        for partner in self:
            stats = record.get(partner) or {"deals": 0, "won": 0, "lost": 0, "gap": 0.0}
            deals = stats["deals"]
            partner.competitor_deal_count = deals
            partner.competitor_won_count = stats["won"]
            partner.competitor_lost_count = stats["lost"]
            partner.competitor_win_rate = 100.0 * stats["won"] / deals if deals else 0.0
            partner.competitor_price_gap = stats["gap"] / deals if deals else 0.0

    def action_view_competitor_offers(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Offers of %(competitor)s", competitor=self.name),
            "type": "ir.actions.act_window",
            "res_model": "competitor.offer",
            "view_mode": "list,form",
            "domain": [("competitor_id", "=", self.id)],
            "context": {"default_competitor_id": self.id},
        }
