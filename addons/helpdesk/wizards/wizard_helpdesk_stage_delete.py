from odoo import api, fields, models


class WizardHelpdeskStageDelete(models.TransientModel):
    _name = "wizard.helpdesk.stage.delete"
    _description = "Helpdesk Stage Delete Wizard"

    team_ids = fields.Many2many(
        comodel_name="team.team",
        string="Helpdesk Teams",
        domain="[('use_helpdesk', '=', True), '|', ('active', '=', False), ('active', '=', True)]",
    )
    stage_ids = fields.Many2many(
        comodel_name="helpdesk.stage",
        string="Stages To Delete",
    )
    ticket_count = fields.Integer(
        string="Number of Tickets",
        compute="_compute_ticket_count",
    )
    stages_active = fields.Boolean(
        export_string_translation=False,
        compute="_compute_stages_active",
    )

    def _compute_ticket_count(self) -> None:
        HelpdeskTicket = self.with_context(active_test=False).env["helpdesk.ticket"]
        for wizard in self:
            wizard.ticket_count = HelpdeskTicket.search_count(
                [("stage_id", "in", wizard.stage_ids.ids)]
            )

    @api.depends("stage_ids")
    def _compute_stages_active(self) -> None:
        for wizard in self:
            wizard.stages_active = all(wizard.stage_ids.mapped("active"))

    def action_archive(self):
        if len(self.team_ids) <= 1:
            return self.action_confirm()
        return {
            "name": self.env._("Confirmation"),
            "view_mode": "form",
            "res_model": "wizard.helpdesk.stage.delete",
            "views": [
                (
                    self.env.ref(
                        "helpdesk.view_helpdesk_stage_delete_confirmation_wizard"
                    ).id,
                    "form",
                )
            ],
            "type": "ir.actions.act_window",
            "res_id": self.id,
            "target": "new",
            "context": self.env.context,
        }

    def action_confirm(self):
        tickets = (
            self.with_context(active_test=False)
            .env["helpdesk.ticket"]
            .search([("stage_id", "in", self.stage_ids.ids)])
        )
        tickets.write({"active": False})
        self.stage_ids.write({"active": False})
        return self._get_action()

    def action_unarchive_ticket(self) -> None:
        tickets = (
            self.env["helpdesk.ticket"]
            .with_context(active_test=False)
            .search([("stage_id", "in", self.stage_ids.ids)])
        )
        tickets.action_unarchive()

    def action_unlink(self):
        self.stage_ids.unlink()
        return self._get_action()

    def _get_action(self):
        team_id = self.env.context.get("default_team_id")
        if team_id:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "helpdesk.helpdesk_ticket_action_team"
            )
            action["domain"] = [("team_id", "=", team_id)]
            action["context"] = str(
                {
                    "pivot_row_groupby": ["user_id"],
                    "default_team_id": team_id,
                }
            )
        elif self.env.context.get("stage_view"):
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "helpdesk.helpdesk_stage_action"
            )
        else:
            action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
                "helpdesk.helpdesk_ticket_action_main_tree"
            )

        context = dict(
            self.env["ir.actions.actions"]._eval_action_context(action.get("context")),
            active_test=True,
        )
        action["context"] = context
        action["target"] = "main"
        return action
