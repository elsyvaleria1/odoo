from odoo import fields, models


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    # FIELDS
    freight_approval_category_id = fields.Many2one(
        comodel_name="approval.category",
        string="Freight Approval",
        help="A shipping order sent with /embarque prepares a draft request of "
        "this category for the freight. Empty: none is prepared.",
    )
    freight_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Freight Billed By",
        help="Who bills the freight: the vendor of the request and of its bill.",
    )
