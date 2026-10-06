from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    twitter_use_own_account = fields.Boolean(
        string="Use your own X Account",
        config_parameter="social.twitter_use_own_account",
        help="""Check this if you want to use your personal X Developer Account instead of the provided one.""",
    )
    twitter_consumer_key = fields.Char(
        string="X Consumer Key",
        compute="_compute_twitter_consumer_key",
        inverse="_inverse_twitter_consumer_key",
    )
    twitter_consumer_secret_key = fields.Char(
        string="X Consumer Secret Key",
        secret_parameter="social.twitter_consumer_secret_key",
    )

    @api.onchange("twitter_use_own_account")
    def _onchange_twitter_use_own_account(self) -> None:
        if not self.twitter_use_own_account:
            self.twitter_consumer_key = False
            self.twitter_consumer_secret_key = False

    @api.depends("twitter_use_own_account")
    def _compute_twitter_consumer_key(self) -> None:
        for record in self:
            if self.env.user.has_group("social.group_social_manager"):
                record.twitter_consumer_key = self.env.registry.settings.get(
                    self.env, "social.twitter_consumer_key", False
                )
            else:
                record.twitter_consumer_key = None

    def _inverse_twitter_consumer_key(self) -> None:
        for record in self:
            if self.env.user.has_group("social.group_social_manager"):
                self.env["ir.config_parameter"].sudo().set_param(
                    "social.twitter_consumer_key", record.twitter_consumer_key
                )
