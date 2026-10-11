from odoo import api, fields, models


class WizardProjectTaskConvertTicket(models.TransientModel):
    _name = "wizard.project.task.convert.ticket"
    _description = "Convert Project Tasks to Tickets"

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if "team_id" in fields and not result.get("team_id"):
            result["team_id"] = (
                self._get_default_helpdesk_team_id()
                or self.env["team.team"]
                .search([("use_helpdesk", "=", True)], limit=1)
                .id
            )
        return result

    def _get_default_helpdesk_team_id(self):
        return False

    team_id = fields.Many2one(
        comodel_name="team.team",
        domain=[("use_helpdesk", "=", True)],
    )
    stage_id = fields.Many2one(
        comodel_name="helpdesk.stage",
        compute="_compute_default_stage",
        store=True,
        readonly=False,
        required=True,
        domain="[('team_ids', 'in', team_id)]",
    )

    @api.depends("team_id")
    def _compute_default_stage(self) -> None:
        self.stage_id = (
            self.team_id.helpdesk_stage_ids[0].id
            if self.team_id.helpdesk_stage_ids
            else False
        )

    def action_convert(self) -> dict:
        tasks_to_convert = self._get_tasks_to_convert()

        created_tickets = (
            self.env["helpdesk.ticket"]
            .with_context(mail_create_nolog=True)
            .create([self._prepare_ticket_vals(task) for task in tasks_to_convert])
        )

        for task, ticket in zip(tasks_to_convert, created_tickets, strict=False):
            task.active = False

            task_sudo, ticket_sudo = task.sudo(), ticket.sudo()
            task_sudo.message_post(
                body=self.env._(
                    "Task converted into ticket %s", ticket_sudo._get_html_link()
                )
            )
            ticket_sudo.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": ticket_sudo, "origin": task_sudo},
                subtype_xmlid="mail.mt_note",
            )

        if len(created_tickets) == 1:
            return {
                "view_mode": "form",
                "res_model": "helpdesk.ticket",
                "res_id": created_tickets[0].id,
                "views": [(False, "form")],
                "type": "ir.actions.act_window",
            }
        return {
            "name": self.env._("Converted Tickets"),
            "view_mode": "list,form",
            "res_model": "helpdesk.ticket",
            "views": [(False, "list"), (False, "form")],
            "type": "ir.actions.act_window",
            "domain": [("id", "in", created_tickets.ids)],
        }

    def _get_tasks_to_convert(self):
        to_convert_ids = self.env.context.get("to_convert", [])
        return self.env["project.task"].browse(to_convert_ids)

    def _prepare_ticket_vals(self, task) -> dict:
        return {
            "name": task.name,
            "description": task.description,
            "team_id": self.team_id.id,
            "stage_id": self.stage_id.id,
            "partner_id": task.partner_id.id,
        }
