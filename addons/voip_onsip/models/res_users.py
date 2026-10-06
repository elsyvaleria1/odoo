from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    onsip_auth_username = fields.Char(
        compute="_compute_onsip_auth_username",
        inverse="_inverse_voip_settings",
        classification="base.internal",
    )

    @api.depends("res_users_settings_id.onsip_auth_username")
    def _compute_onsip_auth_username(self) -> None:
        for user in self:
            user.onsip_auth_username = user.res_users_settings_id.onsip_auth_username

    @api.model
    def _get_fields_voip_user_configuration(self):
        return super()._get_fields_voip_user_configuration() + [
            "onsip_auth_username",
        ]
