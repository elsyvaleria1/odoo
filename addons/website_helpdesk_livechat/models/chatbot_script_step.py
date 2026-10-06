from odoo import fields, models
from odoo.tools import html2plaintext


class ChatbotScriptStep(models.Model):
    _inherit = "chatbot.script.step"

    step_type = fields.Selection(
        selection_add=[("create_ticket", "Create Ticket")],
        ondelete={"create_ticket": "cascade"},
    )
    helpdesk_team_id = fields.Many2one(
        comodel_name="team.team",
        domain=[("use_helpdesk", "=", True)],
        ondelete="set null",
    )

    def _prepare_ticket_values(self, discuss_channel, description) -> dict:
        name = self.env._(
            "%(name)s's Ticket",
            name=discuss_channel.livechat_visitor_id.display_name
            or self.chatbot_script_id.title,
        )
        if msg := self._find_first_user_free_input(discuss_channel):
            name = html2plaintext(msg.body)[:100]
        return {
            "origin_channel_id": discuss_channel.id,
            "description": description + discuss_channel.sudo()._get_channel_history(),
            "name": name,
            "source_id": self.chatbot_script_id.source_id.id,
            "team_id": self.helpdesk_team_id.id,
        }

    def _process_step(self, discuss_channel):
        self.check_singleton()

        posted_message = super()._process_step(discuss_channel)

        if self.step_type == "create_ticket":
            self._process_step_create_ticket(discuss_channel)

        return posted_message

    def _process_step_create_ticket(self, discuss_channel) -> None:

        customer_values = self._chatbot_prepare_customer_values(
            discuss_channel, create_partner=True, update_partner=True
        )

        self.env["helpdesk.ticket"].create(
            {
                "partner_id": customer_values["partner"].id,
                **self._prepare_ticket_values(
                    discuss_channel, customer_values["description"]
                ),
            }
        )
