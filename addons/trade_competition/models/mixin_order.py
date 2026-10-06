from odoo import fields, models


class MixinOrder(models.AbstractModel):
    _inherit = "mixin.order"

    _competitor_offer_link = ""

    lost_to_id = fields.Many2one(
        comodel_name="res.partner",
        string="Lost To",
        index="btree_not_null",
        copy=False,
        domain=[("is_competitor", "=", True)],
        tracking=True,
        help="The competitor who won the deal this order lost.",
    )

    def _prepare_winning_offer_values(self, competitor, amount):
        self.check_singleton()
        ratio = amount / self.amount_untaxed if self.amount_untaxed else 0.0
        values = {
            "competitor_id": competitor.id,
            "partner_id": self.partner_id.id,
            "direction": self._direction.key,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "source": "customer_feedback",
            "confidence": "reported",
            "is_winner": True,
            "line_ids": [
                fields.Command.create(
                    {
                        "product_id": line.product_id.id,
                        "product_qty": line.product_qty,
                        "product_uom_id": line.product_uom_id.id,
                        "price_unit": line.price_unit
                        * (1 - (line.discount or 0.0) / 100)
                        * ratio,
                    }
                )
                for line in self.line_ids
                if line.product_id and not line.display_type
            ],
        }
        if self._competitor_offer_link:
            values[self._competitor_offer_link] = self.id
        return values
