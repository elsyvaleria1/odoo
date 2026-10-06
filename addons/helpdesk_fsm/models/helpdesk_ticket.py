from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    use_fsm = fields.Boolean(
        related="team_id.helpdesk_use_fsm",
        export_string_translation=False,
    )
    fsm_task_ids = fields.One2many(
        comodel_name="project.task",
        inverse_name="helpdesk_ticket_id",
        string="Tasks",
        copy=False,
        domain=[("is_fsm", "=", True)],
        help="Tasks generated from this ticket",
    )
    fsm_task_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_fsm_task_count",
    )

    @api.depends("fsm_task_ids")
    def _compute_fsm_task_count(self) -> None:
        ticket_groups = self.env["project.task"]._read_group(
            [("is_fsm", "=", True), ("helpdesk_ticket_id", "in", self.ids)],
            ["helpdesk_ticket_id"],
            ["__count"],
        )
        ticket_count_mapping = {
            helpdesk_ticket.id: count for helpdesk_ticket, count in ticket_groups
        }
        for ticket in self:
            ticket.fsm_task_count = ticket_count_mapping.get(ticket.id, 0)

    def action_view_fsm_tasks(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "industry_fsm.project_task_action_all_fsm"
        )
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(
                action.get("context", "{}")
            ),
            create=False,
        )

        if len(self.fsm_task_ids) == 1:
            fsm_form_view = self.env.ref("project.view_task_form2")
            action.update(
                res_id=self.fsm_task_ids[0].id, views=[(fsm_form_view.id, "form")]
            )
        else:
            action.update(
                domain=[("id", "in", self.fsm_task_ids.ids)], name=self.env._("Tasks")
            )
        return action

    def action_generate_fsm_task(self) -> dict:
        self.check_singleton()
        if not self.partner_id and (self.partner_name or self.partner_email):
            self.partner_id = self._partner_get_or_create_from_emails_single(
                [self.partner_email]
            ).id
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Create a Field Service task"),
            "res_model": "wizard.helpdesk.ticket.create.fsm.task",
            "view_mode": "form",
            "target": "new",
            "context": {
                "use_fsm": True,
                "default_helpdesk_ticket_id": self.id,
                "default_user_id": False,
                "default_partner_id": self.partner_id.id,
                "default_name": self.name,
                "default_project_id": self.team_id.sudo().fsm_project_id.id,
                "dialog_size": "medium",
            },
        }

    # ---------------------------------------------------
    # Mail gateway
    # ---------------------------------------------------

    def _mail_get_message_subtypes(self):
        res = super()._mail_get_message_subtypes()
        if len(self) == 1 and self.team_id:
            task_done_subtype = self.env.ref("helpdesk_fsm.mt_ticket_task_done")
            if not self.team_id.helpdesk_use_fsm and task_done_subtype in res:
                res -= task_done_subtype
        return res
