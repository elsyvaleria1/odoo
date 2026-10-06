from odoo import Command, api, models


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams.sudo()._check_helpdesk_sale_timesheet_group()
        return teams

    def write(self, vals):
        result = super().write(vals)
        if "use_helpdesk_sale_timesheet" in vals:
            self.sudo()._check_helpdesk_sale_timesheet_group()
        return result

    def _is_sale_timesheet_feature_enabled(self) -> bool:
        """Check if the Time Billing feature is enabled

        Check if the user can see at least one helpdesk team with `use_helpdesk_sale_timesheet=True`

        :return True if the feature is enabled otherwise False.
        """
        return bool(
            self.env["team.team"].search(
                [("use_helpdesk_sale_timesheet", "=", True)], limit=1
            )
        )

    def _check_helpdesk_sale_timesheet_group(self) -> None:
        use_sale_timesheet_group = self.env.ref(
            "helpdesk_sale.group_use_helpdesk_sale_timesheet"
        )
        sale_teams = self.filtered("use_helpdesk_sale_timesheet")
        user_has_use_sale_timesheet_group = self.env.user.has_group(
            "helpdesk_sale.group_use_helpdesk_sale_timesheet"
        )

        if sale_teams and not user_has_use_sale_timesheet_group:
            self._get_helpdesk_user_group().write(
                {"implied_ids": [Command.link(use_sale_timesheet_group.id)]}
            )
        elif (
            not sale_teams
            and user_has_use_sale_timesheet_group
            and not self._is_sale_timesheet_feature_enabled()
        ):
            self._get_helpdesk_user_group().write(
                {"implied_ids": [Command.unlink(use_sale_timesheet_group.id)]}
            )
            self.env["res.users.grant"]._revoke(
                None, use_sale_timesheet_group, reason="no team uses the feature"
            )
