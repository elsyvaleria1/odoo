from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["mixin.order.line.competition", "purchase.order.line"]

    market_price = fields.Float(
        help="The highest comparable price a rival buyer offers for this product: "
        "to this vendor when known, else to its industry, else to the market. "
        "Per this line's unit.",
    )
    market_scope = fields.Selection(
        selection=[
            ("partner", "This Vendor"),
            ("segment", "Its Industry"),
            ("market", "Market"),
        ],
    )
    limit_price = fields.Float(
        string="Ceiling Price",
        help="Our resale price less the minimum margin: the highest price to pay.",
    )
    recommended_price = fields.Float(
        help="The market price plus the overbid, never above the ceiling.",
    )

    def _market_depends(self) -> list:
        return [*super()._market_depends(), "product_id.lst_price"]

    def _competition_settings(self, company) -> dict:
        config = company.purchase_config_id
        return {
            "min_margin": config.competition_min_margin,
            "step": config.competition_overbid,
            "leader_gap": config.competition_leader_gap,
        }

    def _competition_limit(self, company, date, settings):
        resale = self.product_id.lst_price
        if not resale:
            return 0.0
        margin = self.product_id.categ_id.purchase_min_margin or settings["min_margin"]
        return resale / (1 + margin / 100)
