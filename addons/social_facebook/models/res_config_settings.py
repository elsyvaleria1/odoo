from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    facebook_use_own_account = fields.Boolean(
        string="Use your own Facebook Account",
        config_parameter="social.facebook_use_own_account",
        help="""Check this if you want to use your personal Facebook Developer Account instead of the provided one.""",
    )
    facebook_app_id = fields.Char(
        string="Facebook App ID",
        compute="_compute_facebook_app_id",
        inverse="_inverse_facebook_app_id",
    )
    facebook_client_secret = fields.Char(
        string="Facebook App Secret",
        secret_parameter="social.facebook_client_secret",
    )

    @api.onchange("facebook_use_own_account")
    def _onchange_facebook_use_own_account(self) -> None:
        if not self.facebook_use_own_account:
            self.facebook_app_id = False
            self.facebook_client_secret = False

    @api.depends("facebook_use_own_account")
    def _compute_facebook_app_id(self) -> None:
        for record in self:
            if self.env.user.has_group("social.group_social_manager"):
                record.facebook_app_id = self.env.registry.settings.get(
                    self.env, "social.facebook_app_id", False
                )
            else:
                record.facebook_app_id = None

    def _inverse_facebook_app_id(self) -> None:
        for record in self:
            if self.env.user.has_group("social.group_social_manager"):
                self.env["ir.config_parameter"].sudo().set_param(
                    "social.facebook_app_id", record.facebook_app_id
                )
