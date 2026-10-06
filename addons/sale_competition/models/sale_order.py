from odoo import api, fields, models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["mixin.order.competition", "sale.order"]

    _competitor_offer_link = "sale_order_id"

    competitor_offer_ids = fields.One2many(
        comodel_name="competitor.offer",
        inverse_name="sale_order_id",
        string="Competitor Offers",
    )
    competitor_offer_count = fields.Count(
        count_of="competitor_offer_ids",
        string="Competitor Offer Count",
    )
    competitor_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="sale_order_competitor_rel",
        string="Competitors",
        compute="_compute_competitor_ids",
        store=True,
        help="The competitors whose offers compete with this quotation.",
    )
    market_position = fields.Selection(
        help="The least favourable position among the quotation's lines.",
    )
    price_gap_at_close = fields.Float(
        help="The quotation's gap to the market, weighted by line, when it was "
        "won or lost.",
    )

    @api.depends("competitor_offer_ids.competitor_id")
    def _compute_competitor_ids(self) -> None:
        for order in self:
            order.competitor_ids = order.competitor_offer_ids.competitor_id
