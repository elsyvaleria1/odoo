from odoo import Command, api, models


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams.sudo()._check_website_helpdesk_livechat_group()
        return teams

    def write(self, vals):
        result = super().write(vals)
        if "use_website_helpdesk_livechat" in vals:
            self.sudo()._check_website_helpdesk_livechat_group()
        return result

    def _get_field_check_method(self):
        check_methods = super()._get_field_check_method()
        check_methods["use_website_helpdesk_livechat"] = (
            self._is_website_helpdesk_livechat_feature_enabled
        )
        return check_methods

    def _is_website_helpdesk_livechat_feature_enabled(
        self, check_user_has_group=False
    ) -> bool:
        user_has_group = (
            self.env.user.has_group("im_livechat.im_livechat_group_user")
            if check_user_has_group
            else True
        )
        return bool(
            user_has_group
            and self.env["team.team"].search(
                [("use_website_helpdesk_livechat", "=", True)], limit=1
            )
        )

    def _check_website_helpdesk_livechat_group(self) -> None:
        use_website_helpdesk_livechat_group = self.env.ref(
            "website_helpdesk_livechat.group_use_website_helpdesk_livechat"
        )
        livechat_teams = self.filtered("use_website_helpdesk_livechat")
        non_livechat_teams = self - livechat_teams
        user_has_use_livechat_group = self.env.user.has_group(
            "website_helpdesk_livechat.group_use_website_helpdesk_livechat"
        )

        if livechat_teams and not user_has_use_livechat_group:
            self._get_helpdesk_user_group().write(
                {"implied_ids": [Command.link(use_website_helpdesk_livechat_group.id)]}
            )
        if (
            non_livechat_teams
            and user_has_use_livechat_group
            and not self._is_website_helpdesk_livechat_feature_enabled()
        ):
            self._get_helpdesk_user_group().write(
                {
                    "implied_ids": [
                        Command.unlink(use_website_helpdesk_livechat_group.id)
                    ]
                }
            )
            self.env["res.users.grant"]._revoke(
                None,
                use_website_helpdesk_livechat_group,
                reason="no team uses the feature",
            )
