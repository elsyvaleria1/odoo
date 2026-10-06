from odoo import api, fields, models


class WizardHelpdeskTicketCreateFsmTask(models.TransientModel):
    _name = "wizard.helpdesk.ticket.create.fsm.task"
    _description = "Create a Field Service task"

    helpdesk_ticket_id = fields.Many2one(
        comodel_name="helpdesk.ticket",
        string="Related ticket",
        required=True,
    )
    company_id = fields.Many2one(
        related="helpdesk_ticket_id.company_id",
        export_string_translation=False,
    )
    name = fields.Char(
        string="Title",
        required=True,
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        required=True,
        domain="[('company_id', '=', company_id), ('is_fsm', '=', True), ('is_template', '=', False)]",
        help="Project in which to create the task",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Ticket's customer, will be linked to the task",
    )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if "project_id" in fields and not defaults.get("project_id"):
            task_default = (
                self.env["project.task"]
                .with_context(fsm_mode=True)
                .default_get(["project_id"])
            )
            defaults.update({"project_id": task_default.get("project_id", False)})
        partner_id = defaults.get("partner_id")
        if partner_id:
            delivery = (
                self.env["res.partner"]
                .browse(partner_id)
                .address_get(["delivery"])
                .get("delivery")
            )
            if delivery:
                defaults.update({"partner_id": delivery})
        return defaults

    def _generate_task_values(self):
        self.check_singleton()
        return {
            "name": self.name,
            "helpdesk_ticket_id": self.helpdesk_ticket_id.id,
            "project_id": self.project_id.id,
            "partner_id": self.partner_id.id,
            "description": self.helpdesk_ticket_id.description,
        }

    def action_generate_task(self):
        self.check_singleton()
        ticket = self.helpdesk_ticket_id
        if not ticket.partner_id:
            ticket.partner_id = self.partner_id
        new_task = self.env["project.task"].create(self._generate_task_values())
        ticket.message_post_with_source(
            "helpdesk.ticket_conversion_link",
            render_values={
                "created_record": new_task,
                "message": self.env._("Task created"),
            },
            subtype_xmlid="mail.mt_note",
        )
        return new_task

    def action_generate_and_view_task(self) -> dict:
        self.check_singleton()
        new_task = self.action_generate_task()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Tasks from Tickets"),
            "res_model": "project.task",
            "res_id": new_task.id,
            "view_mode": "form",
            "view_id": self.env.ref("project.view_task_form2").id,
            "context": {
                "fsm_mode": True,
                "create": False,
            },
        }
