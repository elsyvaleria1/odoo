from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    stock_auto_validate_on_approval = fields.Boolean(
        string="Auto-Validate on Approval",
        default=False,
        help="Automatically validate stock transfer when all approvals are granted",
    )
