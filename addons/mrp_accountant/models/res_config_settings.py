from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    account_production_wip_account_id = fields.Many2one(
        comodel_name="account.account",
        related="company_id.stock_config_id.account_production_wip_account_id",
        string="WIP Account",
        readonly=False,
    )

    account_production_wip_overhead_account_id = fields.Many2one(
        comodel_name="account.account",
        related="company_id.stock_config_id.account_production_wip_overhead_account_id",
        string="WIP Overhead Account",
        readonly=False,
    )
