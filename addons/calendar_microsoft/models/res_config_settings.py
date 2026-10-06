from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cal_microsoft_sync_paused = fields.Boolean(
        string="Microsoft Synchronization Paused",
        config_parameter="microsoft_calendar_sync_paused",
        help="Indicates if synchronization with Outlook Calendar is paused or not.",
    )
