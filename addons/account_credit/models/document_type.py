from odoo import fields, models


class DocumentType(models.Model):
    _inherit = "document.type"

    has_amount = fields.Boolean(
        help="Check if documents of this type carry a monetary amount"
    )
    has_collateral = fields.Boolean(
        help="Check if documents of this type require a collateral amount field"
    )
    has_guarantor = fields.Boolean(
        help="Check if documents of this type show the guarantor flag"
    )
