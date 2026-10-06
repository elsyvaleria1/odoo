from odoo import fields, models


class MixinOrderLoss(models.AbstractModel):
    _inherit = "mixin.order.loss"

    lost_to_id = fields.Many2one(
        comodel_name="res.partner",
        string="Won By",
        domain=[("is_competitor", "=", True)],
        help="The competitor who won. Recording them keeps their offer in the "
        "market prices.",
    )
    winning_amount = fields.Float(
        string="Their Total",
        digits="Product Price",
        help="The winner's untaxed total, in the order's currency. Their offer's "
        "lines take it in proportion to ours; correct them on the offer when "
        "known line by line.",
    )

    def action_close(self):
        result = super().action_close()
        if self.lost_to_id and self.outcome == "lost":
            self.order_ids.lost_to_id = self.lost_to_id
            if self.winning_amount:
                self.env["competitor.offer"].create(
                    [
                        order._prepare_winning_offer_values(
                            self.lost_to_id, self.winning_amount
                        )
                        for order in self.order_ids
                    ]
                )
        return result
