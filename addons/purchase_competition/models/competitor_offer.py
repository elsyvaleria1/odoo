from odoo import fields, models


class CompetitorOffer(models.Model):
    _inherit = "competitor.offer"

    purchase_order_id = fields.Many2one(
        comodel_name="purchase.order",
        string="Request for Quotation",
        index="btree_not_null",
        check_company=True,
        help="Our request for quotation this offer competes with.",
    )

    def _competition_order_models(self) -> list:
        return [*super()._competition_order_models(), "purchase.order"]
