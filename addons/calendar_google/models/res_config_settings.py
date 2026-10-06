from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cal_sync_paused = fields.Boolean(
        string="Google Synchronization Paused",
        config_parameter="google_calendar_sync_paused",
        help="Indicates if synchronization with Google Calendar is paused or not.",
    )
