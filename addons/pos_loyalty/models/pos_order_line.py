from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    is_reward_line = fields.Boolean(
        help="Whether this line is part of a reward or not."
    )
    reward_id = fields.Many2one(
        comodel_name="loyalty.reward",
        index="btree_not_null",
        ondelete="restrict",
        help="The reward associated with this line.",
    )
    coupon_id = fields.Many2one(
        comodel_name="loyalty.card",
        ondelete="restrict",
        help="The coupon used to claim that reward.",
    )
    reward_identifier_code = fields.Char(
        help="""
        Technical field used to link multiple reward lines from the same reward together.
    """
    )
    points_cost = fields.Float(help="How many point this reward cost on the coupon.")

    def _get_pricing_exemptions(self):
        exemptions = super()._get_pricing_exemptions()
        topped_up = (
            self.env["loyalty.program"]
            .search(
                [
                    ("program_type", "in", ("gift_card", "ewallet")),
                    ("trigger_product_ids", "in", self.product_id.ids),
                ]
            )
            .trigger_product_ids
        )
        for line in self:
            if line.is_reward_line:
                exemptions[line] |= {"price_unit", "discount", "tax_ids"}
            elif line.product_id in topped_up:
                exemptions[line].add("price_unit")
        return exemptions

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += [
            "is_reward_line",
            "reward_id",
            "reward_identifier_code",
            "points_cost",
            "coupon_id",
        ]
        return params
