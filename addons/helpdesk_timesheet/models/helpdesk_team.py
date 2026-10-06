from collections import defaultdict

from odoo import Command, api, fields, models


class HelpdeskTeam(models.Model):
    _inherit = "team.team"

    project_id = fields.Many2one(
        comodel_name="project.project",
        index="btree_not_null",
        domain="[('allow_timesheets', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id), ('is_template', '=', False)]",
        ondelete="restrict",
        help="Project to which the timesheets of this helpdesk team's tickets will be linked.",
    )
    timesheet_encode_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="company_id.hr_timesheet_config_id.timesheet_encode_uom_id",
        export_string_translation=False,
    )
    total_timesheet_time = fields.Integer(
        export_string_translation=False,
        compute="_compute_total_timesheet_time",
        compute_sudo=True,
        groups="hr_timesheet.group_hr_timesheet_user",
    )

    @api.depends("ticket_ids")
    def _compute_total_timesheet_time(self) -> None:
        helpdesk_timesheet_teams = self.filtered("use_helpdesk_timesheet")
        if not helpdesk_timesheet_teams:
            self.total_timesheet_time = 0.0
            return
        helpdesk_tickets = self.env["helpdesk.ticket"].search(
            [
                ("team_id", "in", helpdesk_timesheet_teams.ids),
                ("fold", "=", False),
            ]
        )
        timesheets_read_group = self.env["account.analytic.line"]._read_group(
            [("helpdesk_ticket_id", "in", helpdesk_tickets.ids)],
            ["helpdesk_ticket_id", "product_uom_id"],
            ["unit_amount:sum"],
        )

        total_by_team = defaultdict(float)
        for helpdesk_ticket, product_uom_id, unit_amount_sum in timesheets_read_group:
            team = helpdesk_ticket.team_id
            uom_team = team.timesheet_encode_uom_id
            product_uom_factor = (product_uom_id or uom_team).factor
            total_by_team[team.id] += (
                unit_amount_sum
                if helpdesk_ticket.encode_uom_in_days
                else unit_amount_sum * product_uom_factor
            ) / uom_team.factor

        for team in self:
            team.total_timesheet_time = round(total_by_team[team.id])

    def _create_project(self, name, allow_billable, other):
        return (
            self.env["project.project"]
            .with_context(default_use_documents=False)
            .create(
                {
                    "name": name,
                    "workflow_step_ids": [
                        Command.create({"name": self.env._("New")}),
                    ],
                    "allow_timesheets": True,
                    **other,
                }
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("use_helpdesk_timesheet") and not vals.get("project_id"):
                allow_billable = vals.get("use_helpdesk_sale_timesheet")
                vals["project_id"] = self._create_project(
                    vals["name"], allow_billable, {}
                ).id
        teams = super().create(vals_list)
        teams.sudo()._check_timesheet_group()
        return teams

    def write(self, vals):
        if "use_helpdesk_timesheet" in vals and not vals["use_helpdesk_timesheet"]:
            vals["project_id"] = False
            # to unlink timer when use_helpdesk_timesheet is false
            self.env["timer.timer"].search(
                [
                    ("res_model", "=", "helpdesk.ticket"),
                    (
                        "res_id",
                        "in",
                        self.with_context(active_test=False).ticket_ids.ids,
                    ),
                ]
            ).unlink()
        result = super().write(vals)
        if "use_helpdesk_timesheet" in vals:
            self.sudo()._check_timesheet_group()
        for team in self.filtered(
            lambda team: team.use_helpdesk_timesheet and not team.project_id
        ):
            team.project_id = team._create_project(
                team.name, team.use_helpdesk_sale_timesheet, {}
            )
        return result

    def _get_timesheet_user_group(self):
        return self.env.ref("hr_timesheet.group_hr_timesheet_user")

    def _check_timesheet_group(self) -> None:
        timesheet_teams = self.filtered("use_helpdesk_timesheet")
        use_helpdesk_timesheet_group = self.env.user.has_group(
            "helpdesk_timesheet.group_use_helpdesk_timesheet"
        )
        helpdesk_timesheet_group = self.env.ref(
            "helpdesk_timesheet.group_use_helpdesk_timesheet"
        )

        def enabled_timesheet_team():
            return self.env["team.team"].search(
                [("use_helpdesk_timesheet", "=", True)], limit=1
            )

        if timesheet_teams and not use_helpdesk_timesheet_group:
            (self._get_helpdesk_user_group() + self._get_timesheet_user_group()).write(
                {"implied_ids": [Command.link(helpdesk_timesheet_group.id)]}
            )
        elif (
            self - timesheet_teams
            and use_helpdesk_timesheet_group
            and not enabled_timesheet_team()
        ):
            (self._get_helpdesk_user_group() + self._get_timesheet_user_group()).write(
                {"implied_ids": [Command.unlink(helpdesk_timesheet_group.id)]}
            )
            self.env["res.users.grant"]._revoke(
                None, helpdesk_timesheet_group, reason="no team uses the feature"
            )

    def action_view_timesheets(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk_timesheet.act_hr_timesheet_line_helpdesk"
        )
        helpdesk_tickets = self.env["helpdesk.ticket"].search(
            [
                ("team_id", "in", self.ids),
                ("fold", "=", False),
            ]
        )
        action.update(
            {
                "domain": [("helpdesk_ticket_id", "in", helpdesk_tickets.ids)],
                "context": {
                    "default_project_id": self.project_id.id,
                    "graph_groupbys": ["date:week", "employee_id"],
                },
            }
        )
        return action
