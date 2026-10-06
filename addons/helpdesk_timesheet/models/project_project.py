from odoo import api, fields, models


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    ticket_ids = fields.One2many(
        comodel_name="helpdesk.ticket",
        inverse_name="project_id",
        string="Tickets",
    )
    ticket_count = fields.Integer(
        string="# Tickets",
        compute="_compute_ticket_count",
        groups="helpdesk.group_helpdesk_user",
    )

    helpdesk_team = fields.One2many(
        comodel_name="team.team",
        inverse_name="project_id",
    )
    has_helpdesk_team = fields.Boolean(
        string="Has Helpdesk Teams",
        export_string_translation=False,
        compute="_compute_has_helpdesk_team",
        search="_search_has_helpdesk_team",
        compute_sudo=True,
    )

    @api.depends("ticket_ids.project_id")
    def _compute_ticket_count(self) -> None:
        result = self.env["helpdesk.ticket"]._read_group(
            [("project_id", "in", self.ids)], ["project_id"], ["__count"]
        )
        data = {project.id: count for project, count in result}
        for project in self:
            project.ticket_count = data.get(project.id, 0)

    @api.depends("helpdesk_team.project_id")
    def _compute_has_helpdesk_team(self) -> None:
        result = self.env["team.team"]._read_group(
            [("project_id", "in", self.ids)], ["project_id"], ["__count"]
        )
        data = {project.id: count for project, count in result}
        for project in self:
            project.has_helpdesk_team = data.get(project.id, False)

    def _search_has_helpdesk_team(self, operator, value):
        if operator != "in":
            return NotImplemented

        helpdesk_team_ids = (
            self.env["team.team"]
            ._read_group(
                [("use_helpdesk_timesheet", "=", True), ("project_id", "!=", False)],
                [],
                ["project_id:recordset"],
            )[0][0]
            .ids
        )
        return [("id", "in", helpdesk_team_ids)]

    def action_view_project_tickets(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk_timesheet.project_project_action_view_helpdesk_tickets"
        )
        action.update(
            {
                "display_name": self.env._("Tickets"),
                "domain": [("id", "in", self.ticket_ids.ids)],
                "context": {"active_id": self.id},
            }
        )
        if len(self.ticket_ids.ids) == 1:
            action["view_mode"] = "form"
            action["views"] = [[False, "form"]]
            action["res_id"] = self.ticket_ids.id
        return action

    # ----------------------------
    #  Project Updates
    # ----------------------------

    def _get_stat_buttons(self):
        buttons = super()._get_stat_buttons()
        if self.env.user.has_group("helpdesk.group_helpdesk_user"):
            buttons.append(
                {
                    "icon": "life-ring",
                    "text": self.env._("Tickets"),
                    "number": self.ticket_count,
                    "action_type": "object",
                    "action": "action_view_project_tickets",
                    "show": self.ticket_count > 0,
                    "sequence": 25,
                }
            )
        return buttons
