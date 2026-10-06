from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    collection_hold_credit_sales = fields.Boolean(
        related="company_id.account_config_id.collection_hold_credit_sales",
        readonly=False,
    )
