from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"



    extra_hour = fields.Float(
        string="Per Hour",
        default=0.0,
    )
    extra_day = fields.Float(
        string="Per Day",
        default=0.0,
    )
    min_extra_hour = fields.Integer(
        string="Minimum delay time before applying fines.",
        default=2,
    )

    extra_product = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        domain="[('type', '=', 'service')]",
        help="The product is used to add the cost to the sales order",
    )

    _min_extra_hour = models.Constraint(
        "CHECK(min_extra_hour >= 1)",
        "Minimal delay time before applying fines has to be positive.",
    )
