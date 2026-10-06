from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    stock_auto_validate_on_approval = fields.Boolean(
        related="company_id.stock_auto_validate_on_approval",
        string="Auto-Validate on Approval",
        readonly=False,
    )
