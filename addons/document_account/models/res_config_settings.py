from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    account_folder_id = fields.Many2one(
        related="company_id.account_folder_id",
        string="account default folder",
        readonly=False,
    )
