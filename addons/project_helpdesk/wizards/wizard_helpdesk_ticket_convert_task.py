from odoo import api, fields, models


class WizardHelpdeskTicketConvertTask(models.TransientModel):
    _name = "wizard.helpdesk.ticket.convert.task"
    _description = "Convert Helpdesk Tickets to Tasks"

    @api.model
    def default_get(self, fields):
        result = super().default_get(fields)
        if "project_id" in fields and not result.get("project_id"):
            result["project_id"] = (
                self._get_default_project_id()
                or self.env["project.project"].search([], limit=1).id
            )
        return result

    def _get_default_project_id(self):
        return False

    project_id = fields.Many2one(
        comodel_name="project.project",
        domain=[("is_template", "=", False)],
    )
    step_id = fields.Many2one(
        comodel_name="project.workflow.step",
        compute="_compute_default_step",
        store=True,
        readonly=False,
        required=True,
        domain="[('project_ids', 'in', project_id)]",
    )

    @api.depends("project_id")
    def _compute_default_step(self) -> None:
        self.step_id = (
            self.project_id.workflow_step_ids[0].id
            if self.project_id.workflow_step_ids
            else False
        )

    def action_convert(self) -> dict:
        tickets_to_convert = self._get_tickets_to_convert()

        created_tasks = (
            self.env["project.task"]
            .with_context(mail_create_nolog=True)
            .create([self._prepare_task_vals(ticket) for ticket in tickets_to_convert])
        )

        for ticket, task in zip(tickets_to_convert, created_tasks, strict=False):
            ticket.active = False

            ticket_sudo, task_sudo = ticket.sudo(), task.sudo()
            ticket_sudo.message_post(
                body=self.env._(
                    "Ticket converted into task %s", task_sudo._get_html_link()
                )
            )
            task_sudo.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": task_sudo, "origin": ticket_sudo},
                subtype_xmlid="mail.mt_note",
            )

        if len(created_tasks) == 1:
            return {
                "view_mode": "form",
                "res_model": "project.task",
                "res_id": created_tasks[0].id,
                "views": [(self.env.ref("project.view_task_form2").id, "form")],
                "type": "ir.actions.act_window",
            }
        return {
            "name": self.env._("Converted Tasks"),
            "view_mode": "list,form",
            "res_model": "project.task",
            "views": [
                (self.env.ref("project.view_task_tree2").id, "list"),
                (self.env.ref("project.view_task_form2").id, "form"),
            ],
            "type": "ir.actions.act_window",
            "domain": [("id", "in", created_tasks.ids)],
        }

    def _get_tickets_to_convert(self):
        to_convert_ids = self.env.context.get("to_convert", [])
        return self.env["helpdesk.ticket"].browse(to_convert_ids)

    def _prepare_task_vals(self, ticket) -> dict:
        return {
            "name": ticket.name,
            "description": ticket.description,
            "project_id": self.project_id.id,
            "step_id": self.step_id.id,
            "partner_id": ticket.partner_id.id,
        }
