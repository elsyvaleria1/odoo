from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict


class MixinAgreementLineBreak(models.AbstractModel):
    _name = "mixin.agreement.line.break"
    _description = "Agreement Quantity Break"
    _order = "line_id, min_qty"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("agreement_id.company_id", shared=False),
        }
    )

    agreement_id = fields.Many2one(
        comodel_name="mixin.agreement",
        index=True,
        required=True,
        ondelete="cascade",
    )
    line_id = fields.Many2one(
        comodel_name="mixin.agreement.line",
        string="Product",
        index=True,
        required=True,
        domain="[('agreement_id', '=', agreement_id)]",
        ondelete="cascade",
    )
    currency_id = fields.Many2one(related="agreement_id.currency_id")
    product_uom_id = fields.Many2one(related="line_id.product_uom_id")
    min_qty = fields.Float(
        string="From Quantity",
        digits="Product Unit",
        required=True,
        help="The quantity an order line must reach, in the agreement line's unit, "
        "for this price to apply.",
    )
    price_unit = fields.Float(
        string="Unit Price",
        min_display_digits="Product Price",
        required=True,
    )

    @api.constrains("min_qty", "price_unit", "line_id")
    def _check_break(self) -> None:
        for rule in self:
            if rule.min_qty <= 0.0 or rule.price_unit <= 0.0:
                raise ValidationError(
                    self.env._(
                        "A quantity break needs a quantity and a price above zero."
                    )
                )
            if rule.line_id.agreement_id != rule.agreement_id:
                raise ValidationError(
                    self.env._("A quantity break belongs to a line of its agreement.")
                )
            twins = rule.line_id.break_ids.filtered(
                lambda other, rule=rule: other != rule and other.min_qty == rule.min_qty
            )
            if twins:
                raise ValidationError(
                    self.env._(
                        "%(product)s already has a price from %(qty)s.",
                        product=rule.line_id.product_id.display_name,
                        qty=rule.min_qty,
                    )
                )
