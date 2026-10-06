from odoo import Command, fields, models
from odoo.tools.misc import unique


class HelpdeskStage(models.Model):
    _name = "helpdesk.stage"
    _description = "Helpdesk Stage"
    _order = "sequence, id"

    def _default_team_ids(self):
        defaults = self.env["team.team"]._drop_default_of_other_usage(
            {"team_id": self.env.context.get("default_team_id")}, "helpdesk"
        )
        return [Command.link(team_id)] if (team_id := defaults.get("team_id")) else []

    active = fields.Boolean(default=True)
    name = fields.Char(
        translate=True,
        required=True,
    )
    description = fields.Text(translate=True)
    sequence = fields.Integer(
        export_string_translation=False,
        default=10,
    )
    fold = fields.Boolean(
        string="Folded",
        help="Tickets in a folded stage are considered as closed.",
    )
    team_ids = fields.Many2many(
        comodel_name="team.team",
        relation="team_stage_rel",
        string="Helpdesk Teams",
        default=lambda self: self._default_team_ids(),
        required=True,
        domain=[("use_helpdesk", "=", True)],
    )
    template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Email Template",
        domain="[('model', '=', 'helpdesk.ticket')]",
        help="Email automatically sent to the customer when the ticket reaches this stage.\n"
        "By default, the email will be sent from the email alias of the helpdesk team.\n"
        "Otherwise it will be sent from the company's email address, or from the catchall (as defined in the System Parameters).",
    )
    rotting_threshold_days = fields.Integer(
        string="Days to rot",
        default=0,
        help="Highlight tickets that haven't been updated for this many days.",
    )
    legend_blocked = fields.Char(
        string="Red Kanban Label",
        translate=True,
        default=lambda s: s.env._("Blocked"),
        required=True,
    )
    legend_done = fields.Char(
        string="Green Kanban Label",
        translate=True,
        default=lambda s: s.env._("Ready"),
        required=True,
    )
    legend_normal = fields.Char(
        string="Grey Kanban Label",
        translate=True,
        default=lambda s: s.env._("In Progress"),
        required=True,
    )
    ticket_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_ticket_count",
    )
    color = fields.Integer(export_string_translation=False)

    def _compute_ticket_count(self) -> None:
        res = self.env["helpdesk.ticket"]._read_group(
            [("stage_id", "in", self.ids)], ["stage_id"], ["__count"]
        )
        stage_data = {stage.id: count for stage, count in res}
        for stage in self:
            stage.ticket_count = stage_data.get(stage.id, 0)

    def write(self, vals):
        if "active" in vals and not vals["active"]:
            self.env["helpdesk.ticket"].search([("stage_id", "in", self.ids)]).write(
                {"active": False}
            )
        return super().write(vals)

    def action_unarchive(self):
        res = super().action_unarchive()
        stage_active = self.filtered(self._active_name)
        if (
            stage_active
            and sum(stage_active.with_context(active_test=False).mapped("ticket_count"))
            > 0
        ):
            wizard = self.env["wizard.helpdesk.stage.delete"].create(
                {
                    "stage_ids": stage_active.ids,
                }
            )

            return {
                "name": self.env._("Unarchive Tickets"),
                "view_mode": "form",
                "res_model": "wizard.helpdesk.stage.delete",
                "views": [
                    (
                        self.env.ref(
                            "helpdesk.view_helpdesk_stage_unarchive_wizard"
                        ).id,
                        "form",
                    )
                ],
                "type": "ir.actions.act_window",
                "res_id": wizard.id,
                "target": "new",
            }
        return res

    def action_unlink_wizard(self, stage_view=False) -> dict:
        self = self.with_context(active_test=False)
        # retrieves all the teams with a least 1 ticket in that stage
        # a ticket can be in a stage even if the team is not assigned to the stage
        readgroup = (
            self.with_context(active_test=False)
            .env["helpdesk.ticket"]
            ._read_group(
                [("stage_id", "in", self.ids), ("team_id", "!=", False)], ["team_id"]
            )
        )
        team_ids = list(unique([team.id for [team] in readgroup] + self.team_ids.ids))

        wizard = self.env["wizard.helpdesk.stage.delete"].create(
            {"team_ids": team_ids, "stage_ids": self.ids}
        )

        context = dict(self.env.context)
        context["stage_view"] = stage_view
        return {
            "name": self.env._("Delete Stage"),
            "view_mode": "form",
            "res_model": "wizard.helpdesk.stage.delete",
            "views": [
                (self.env.ref("helpdesk.view_helpdesk_stage_delete_wizard").id, "form")
            ],
            "type": "ir.actions.act_window",
            "res_id": wizard.id,
            "target": "new",
            "context": context,
        }

    def action_view_helpdesk_ticket(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_ticket_action_main_tree"
        )
        action.update(
            {
                "domain": [("stage_id", "in", self.ids)],
                "context": {
                    "default_stage_id": self.id,
                },
            }
        )
        return action
