from odoo import api, fields, models

from odoo.addons.trade.tools import direction_of
from odoo.addons.trade_competition.tools import from_comparable


class MixinOrderLinePriceHistory(models.AbstractModel):
    _inherit = "mixin.order.line.price.history"

    competitor_best_price = fields.Monetary(
        string="Best Competitor Price",
        currency_field="currency_id",
        compute="_compute_competition",
        help="The best comparable price competitors offered in the period: the "
        "lowest when we sell, the highest when we buy. Per the product's "
        "reference unit, in the currency above.",
    )
    competitor_avg_price = fields.Monetary(
        string="Average Competitor Price",
        currency_field="currency_id",
        compute="_compute_competition",
    )
    competitor_partner_price = fields.Monetary(
        string="Best Offered to Them",
        currency_field="currency_id",
        compute="_compute_competition",
        help="The best comparable price competitors offered this partner in the "
        "period.",
    )
    competitor_offer_count = fields.Integer(
        string="Competitor Offers",
        compute="_compute_competition",
    )

    @api.depends("product_id", "partner_id", "period", "currency_id")
    def _compute_competition(self) -> None:
        for wizard in self:
            wizard.update(wizard._get_competition_stats())

    def _get_competition_domain(self) -> list:
        return [
            ("product_id", "=", self.product_id.id),
            (
                "direction",
                "=",
                direction_of(self.env[self._price_history_line_model]).key,
            ),
            ("equivalence", "in", ["same", "comparable"]),
            ("date", ">=", self._get_period_start()),
        ]

    def _get_competition_stats(self):
        self.check_singleton()
        stats = {
            "competitor_best_price": 0.0,
            "competitor_avg_price": 0.0,
            "competitor_partner_price": 0.0,
            "competitor_offer_count": 0,
        }
        if not self.product_id:
            return stats
        lines = self.env["competitor.offer.line"].search(self._get_competition_domain())
        if not lines:
            return stats
        sign = direction_of(self.env[self._price_history_line_model]).price_sign
        company = self.env.company
        today = fields.Date.context_today(self)

        def shown(price):
            return from_comparable(
                price,
                unit=False,
                product=self.product_id,
                currency=self.currency_id,
                company=company,
                date=today,
            )

        prices = lines.mapped("price_comparable")
        stats["competitor_best_price"] = shown(sign * min(sign * p for p in prices))
        stats["competitor_avg_price"] = shown(sum(prices) / len(prices))
        stats["competitor_offer_count"] = len(lines.offer_id)
        commercial = self.partner_id.commercial_partner_id
        own = lines.filtered(
            lambda line: (
                commercial and line.partner_id.commercial_partner_id == commercial
            )
        ).mapped("price_comparable")
        if own:
            stats["competitor_partner_price"] = shown(sign * min(sign * p for p in own))
        return stats

    def action_view_competitor_prices(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._(
                "Competitor prices of %(product)s", product=self.product_id.display_name
            ),
            "type": "ir.actions.act_window",
            "res_model": "competitor.offer.line",
            "view_mode": "list,graph,pivot",
            "domain": self._get_competition_domain(),
        }
