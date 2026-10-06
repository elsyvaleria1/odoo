from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    stock_approval_required = fields.Boolean(
        string="Require Approval for Transfers",
        default=False,
        tracking=True,
        help="If checked, transfers from or to this location will require approval",
    )
