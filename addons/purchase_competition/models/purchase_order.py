from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["mixin.order.competition", "purchase.order"]

    _competitor_offer_link = "purchase_order_id"

    competitor_offer_ids = fields.One2many(
        comodel_name="competitor.offer",
        inverse_name="purchase_order_id",
        string="Competitor Offers",
    )
    competitor_offer_count = fields.Count(
        count_of="competitor_offer_ids",
        string="Competitor Offer Count",
    )
    competitor_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="purchase_order_competitor_rel",
        string="Rival Buyers",
        compute="_compute_competitor_ids",
        store=True,
        help="The rival buyers whose offers compete with this request.",
    )

    @api.depends("competitor_offer_ids.competitor_id")
    def _compute_competitor_ids(self) -> None:
        for order in self:
            order.competitor_ids = order.competitor_offer_ids.competitor_id
