from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    deferred_time_off_manager = fields.Many2one(
        comodel_name="res.users",
        related="company_id.deferred_time_off_manager",
        readonly=False,
        check_company=True,
    )
