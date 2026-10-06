from odoo import fields, models


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["mixin.order.line.competition", "sale.order.line"]

    market_price = fields.Float(
        help="The lowest comparable price a competitor offers for this product: "
        "to this customer when known, else to its industry, else to the market. "
        "Per this line's unit.",
    )
    market_scope = fields.Selection(
        selection=[
            ("partner", "This Customer"),
            ("segment", "Its Industry"),
            ("market", "Market"),
        ],
    )
    limit_price = fields.Float(
        string="Floor Price",
        help="Our cost plus the minimum margin: the lowest price to offer.",
    )
    recommended_price = fields.Float(
        help="The market price less the undercut, never below the floor.",
    )

    def _market_depends(self) -> list:
        return [*super()._market_depends(), "purchase_price"]

    def _competition_settings(self, company) -> dict:
        config = company.sale_config_id
        return {
            "min_margin": config.competition_min_margin,
            "step": config.competition_undercut,
            "leader_gap": config.competition_leader_gap,
        }

    def _competition_limit(self, company, date, settings):
        margin = self.product_id.categ_id.sale_min_margin or settings["min_margin"]
        cost = self._to_comparable(self.purchase_price, company, date)
        return cost * (1 + margin / 100)
