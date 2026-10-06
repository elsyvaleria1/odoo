from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ChatbotScript(models.Model):
    _inherit = "chatbot.script"

    ticket_count = fields.Integer(
        string="Generated Ticket Count",
        export_string_translation=False,
        compute="_compute_ticket_count",
    )

    @api.constrains("script_step_ids")
    @api.onchange("script_step_ids")
    def _check_script_steps(self) -> None:
        for step in self.script_step_ids.sorted("sequence"):
            if step.step_type == "question_email":
                break
            if step.step_type == "create_ticket":
                _debug.logic(
                    "chatbot_script_refused",
                    reason="ticket_before_email",
                    step=step.id,
                )
                raise ValidationError(
                    self.env._(
                        'An "Email" step type must exist before the "Create Ticket" step for a ticket to be created.'
                    )
                )

    def _compute_ticket_count(self) -> None:
        tickets_data = (
            self.env["helpdesk.ticket"]
            .with_context(active_test=False)
            .sudo()
            ._read_group(
                [("source_id", "in", self.source_id.ids)], ["source_id"], ["__count"]
            )
        )
        mapped_tickets = {source.id: count for source, count in tickets_data}
        for script in self:
            script.ticket_count = mapped_tickets.get(script.source_id.id, 0)

    def action_view_tickets(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "helpdesk.helpdesk_ticket_action_main_tree"
        )
        action["domain"] = [("source_id", "=", self.source_id.id)]
        action["context"] = {"create": False}
        return action
