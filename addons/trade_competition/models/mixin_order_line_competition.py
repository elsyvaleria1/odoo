from odoo import api, fields, models

from .mixin_order_competition import POSITIONS
from odoo.addons.trade_competition.tools import from_comparable, to_comparable

# how far behind the market still counts as matching it
MATCH_TOLERANCE = 0.01


class MixinOrderLineCompetition(models.AbstractModel):
    _name = "mixin.order.line.competition"
    _description = "Order Line Measured Against Competitor Offers"

    market_price = fields.Float(
        min_display_digits="Product Price",
        compute="_compute_market",
        help="The best comparable price a competitor offers for this product: to "
        "this counterparty when known, else to its industry, else to the market. "
        "Per this line's unit.",
    )
    market_scope = fields.Selection(
        selection=[
            ("partner", "This Counterparty"),
            ("segment", "Its Industry"),
            ("market", "Market"),
        ],
        compute="_compute_market",
    )
    price_gap = fields.Float(
        string="Gap to Market (%)",
        compute="_compute_market",
        help="How far our net price sits above (positive) or below (negative) "
        "the market price.",
    )
    limit_price = fields.Float(
        min_display_digits="Product Price",
        compute="_compute_market",
    )
    recommended_price = fields.Float(
        min_display_digits="Product Price",
        compute="_compute_market",
    )
    market_position = fields.Selection(
        selection=POSITIONS,
        compute="_compute_market",
    )

    def _market_depends(self) -> list:
        return [
            "product_id",
            "product_uom_id",
            "price_unit",
            "discount",
            "order_id.partner_id",
            "order_id.date_order",
        ]

    @api.depends(lambda self: self._market_depends())
    def _compute_market(self) -> None:
        empty = {
            "market_price": 0.0,
            "market_scope": False,
            "price_gap": 0.0,
            "limit_price": 0.0,
            "recommended_price": 0.0,
            "market_position": False,
        }
        lines = self.filtered(lambda line: line.product_id and not line.display_type)
        (self - lines).update(empty)
        if not lines:
            return
        direction = self._direction
        sign = direction.price_sign
        Market = self.env["competitor.offer.line"]
        for (company, date), group in lines.grouped(
            lambda line: (
                line.order_id.company_id,
                fields.Date.to_date(line.order_id.date_order)
                or fields.Date.context_today(line),
            )
        ).items():
            keys = {(line.product_id, line.order_id.partner_id) for line in group}
            prices = Market._get_market_prices(keys, direction.key, date, company)
            settings = group._competition_settings(company)
            for line in group:
                limit = line._competition_limit(company, date, settings)
                values = {
                    **empty,
                    "limit_price": (
                        line._from_comparable(limit, company, date) if limit else 0.0
                    ),
                }
                market = prices.get((line.product_id, line.order_id.partner_id))
                if not market:
                    line.update(values)
                    continue
                market_company, scope, _offer_line = market
                ours = line._to_comparable(line._net_price(), company, date)
                recommended = market_company * (1 - sign * settings["step"] / 100)
                if limit and sign * (recommended - limit) < 0:
                    recommended = limit
                values.update(
                    {
                        "market_price": line._from_comparable(
                            market_company, company, date
                        ),
                        "market_scope": scope,
                        "price_gap": (
                            100.0 * (ours - market_company) / market_company
                            if market_company
                            else 0.0
                        ),
                        "recommended_price": line._from_comparable(
                            recommended, company, date
                        ),
                        "market_position": _position(
                            ours, market_company, limit, settings["leader_gap"], sign
                        ),
                    }
                )
                line.update(values)

    def _competition_settings(self, company) -> dict:
        return {"step": 0.0, "leader_gap": 0.0}

    def _competition_limit(self, company, date, settings):
        return 0.0

    def _net_price(self):
        return self.price_unit * (1 - (self.discount or 0.0) / 100)

    def _to_comparable(self, price, company, date):
        return to_comparable(
            price,
            unit=self.product_uom_id,
            product=self.product_id,
            currency=self.order_id.currency_id,
            company=company,
            date=date,
        )

    def _from_comparable(self, price, company, date):
        return from_comparable(
            price,
            unit=self.product_uom_id,
            product=self.product_id,
            currency=self.order_id.currency_id,
            company=company,
            date=date,
        )


def _position(ours, market, limit, leader_gap, sign) -> str:
    if not market:
        return "competitive"
    advantage = sign * (market - ours) / market
    if advantage < -MATCH_TOLERANCE:
        if limit and sign * (market - limit) < 0:
            return "cannot_match"
        return "behind"
    if advantage > leader_gap / 100:
        return "leader"
    return "competitive"
