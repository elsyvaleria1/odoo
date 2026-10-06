from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    instagram_use_own_account = fields.Boolean(
        string="Use your own Instagram Account",
        config_parameter="social.instagram_use_own_account",
        help="""Check this if you want to use your personal Instagram Developer Account instead of the provided one.""",
    )
    instagram_app_id = fields.Char(
        string="Instagram App ID",
        compute="_compute_instagram_app_id",
        inverse="_inverse_instagram_app_id",
    )
    instagram_client_secret = fields.Char(
        string="Instagram App Secret",
        secret_parameter="social.instagram_client_secret",
    )

    @api.onchange("instagram_use_own_account")
    def _onchange_instagram_use_own_account(self) -> None:
        if not self.instagram_use_own_account:
            self.instagram_client_secret = False

    @api.depends("instagram_use_own_account")
    def _compute_instagram_app_id(self) -> None:
        for record in self:
            if record._instagram_use_and_check_own_account():
                record.instagram_app_id = self.env.registry.settings.get(
                    self.env, "social.instagram_app_id", False
                )
            else:
                record.instagram_app_id = None

    def _inverse_instagram_app_id(self) -> None:
        for record in self:
            if record._instagram_use_and_check_own_account():
                self.env["ir.config_parameter"].sudo().set_param(
                    "social.instagram_app_id", record.instagram_app_id
                )
            elif self.env.user.has_group("social.group_social_manager"):
                self.env["ir.config_parameter"].sudo().set_param(
                    "social.instagram_app_id", ""
                )

    def _instagram_use_and_check_own_account(self):
        return (
            self.env.user.has_group("social.group_social_manager")
            and self.instagram_use_own_account
        )
