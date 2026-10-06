from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    youtube_use_own_account = fields.Boolean(
        string="Use your own YouTube Account",
        config_parameter="social.youtube_use_own_account",
    )
    youtube_oauth_client_id = fields.Char(
        string="YouTube OAuth Client ID",
        compute="_compute_youtube_oauth_client_id",
        inverse="_inverse_youtube_oauth_client_id",
    )
    youtube_oauth_client_secret = fields.Char(
        string="YouTube OAuth Client Secret",
        secret_parameter="social.youtube_oauth_client_secret",
    )

    @api.onchange("youtube_use_own_account")
    def _onchange_youtube_use_own_account(self) -> None:
        if not self.youtube_use_own_account:
            self.youtube_oauth_client_secret = False

    @api.depends("youtube_use_own_account")
    def _compute_youtube_oauth_client_id(self) -> None:
        for record in self:
            if (
                self.env.user.has_group("social.group_social_manager")
                and record.youtube_use_own_account
            ):
                record.youtube_oauth_client_id = self.env.registry.settings.get(
                    self.env, "social.youtube_oauth_client_id", False
                )
            else:
                record.youtube_oauth_client_id = None

    def _inverse_youtube_oauth_client_id(self) -> None:
        for record in self:
            if (
                self.env.user.has_group("social.group_social_manager")
                and record.youtube_use_own_account
            ):
                self.env["ir.config_parameter"].sudo().set_param(
                    "social.youtube_oauth_client_id", record.youtube_oauth_client_id
                )
            elif self.env.user.has_group("social.group_social_manager"):
                self.env["ir.config_parameter"].sudo().set_param(
                    "social.youtube_oauth_client_id", ""
                )
