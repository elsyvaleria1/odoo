from odoo import api, fields, models


class ResUsersSettings(models.Model):
    _inherit = "res.users.settings"

    calendar_default_privacy = fields.Selection(
        selection=[
            ("public", "Public"),
            ("private", "Private"),
            ("confidential", "Only internal users"),
        ],
        default="public",
        store=True,
        readonly=False,
        required=True,
        help="Default privacy setting for whom the calendar events will be visible.",
    )

    @api.model
    def _get_fields_blacklist(self):
        calendar_fields_blacklist = ["calendar_default_privacy"]
        return super()._get_fields_blacklist() + calendar_fields_blacklist
