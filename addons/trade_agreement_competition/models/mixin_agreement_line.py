from odoo import api, fields, models

from odoo.addons.trade_competition.tools import from_comparable, to_comparable


class MixinAgreementLine(models.AbstractModel):
    _inherit = "mixin.agreement.line"

    market_price = fields.Float(
        min_display_digits="Product Price",
        compute="_compute_market",
        help="The best comparable price competitors offer this product today: to "
        "the agreement's partner when known, else to its industry, else to the "
        "market. Per this line's unit, in the agreement's currency.",
    )
    market_scope = fields.Selection(
        selection=[
            ("partner", "This Partner"),
            ("segment", "Its Industry"),
            ("market", "Market"),
        ],
        compute="_compute_market",
    )
    price_gap = fields.Float(
        string="Gap to Market (%)",
        compute="_compute_market",
        help="How far the agreed price sits above (positive) or below (negative) "
        "the market price.",
    )

    @api.depends(
        "product_id", "product_uom_id", "price_unit", "agreement_id.partner_id"
    )
    def _compute_market(self) -> None:
        self.update({"market_price": 0.0, "market_scope": False, "price_gap": 0.0})
        lines = self.filtered(
            lambda line: line.product_id and line.agreement_id.partner_id
        )
        if not lines:
            return
        direction = self.env[self._fields["agreement_id"].comodel_name]._direction
        today = fields.Date.context_today(self)
        Market = self.env["competitor.offer.line"]
        for company, group in lines.grouped(
            lambda line: line.agreement_id.company_id
        ).items():
            prices = Market._get_market_prices(
                {(line.product_id, line.agreement_id.partner_id) for line in group},
                direction.key,
                today,
                company,
            )
            for line in group:
                market = prices.get((line.product_id, line.agreement_id.partner_id))
                if not market:
                    continue
                market_company, scope, _offer_line = market
                basis = {
                    "unit": line.product_uom_id,
                    "product": line.product_id,
                    "currency": line.agreement_id.currency_id,
                    "company": company,
                    "date": today,
                }
                ours = to_comparable(line.price_unit, **basis)
                line.update(
                    {
                        "market_price": from_comparable(market_company, **basis),
                        "market_scope": scope,
                        "price_gap": (
                            100.0 * (ours - market_company) / market_company
                            if market_company
                            else 0.0
                        ),
                    }
                )
