from odoo import api, fields, models


class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    conversation_ids = fields.One2many(
        comodel_name="conversation.conversation",
        inverse_name="calendar_event_id",
    )
    conversation_count = fields.Integer(compute="_compute_conversation_count")

    @api.depends("conversation_ids")
    def _compute_conversation_count(self) -> None:
        for event in self:
            event.conversation_count = len(event.sudo().conversation_ids)

    def action_start_conversation(self) -> dict:
        self.check_singleton()
        conversation = self.sudo().conversation_ids.sorted("id")[-1:]
        if not conversation:
            organiser = self.user_id or self.env.user
            company = organiser.company_id or self.env.company
            conversation = self.env["conversation.conversation"].create(
                {
                    "name": self.name,
                    "kind": "meeting",
                    "source": "meeting_capture",
                    "calendar_event_id": self.id,
                    "company_id": company.id,
                    "start": self.start,
                    "user_id": organiser.id,
                    "partner_id": self._customer_partner().id,
                    "attendee_ids": [fields.Command.set(self.partner_ids.ids)],
                }
            )
            conversation.message_post(
                body=self.env._("Created from calendar event %s", self.display_name)
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "conversation.conversation",
            "res_id": conversation.id,
            "view_mode": "form",
            "target": "current",
        }

    def _customer_partner(self):
        self.check_singleton()
        for partner in self.partner_ids:
            if not partner._is_colleague():
                return partner
        return self.env["res.partner"]

    def action_view_conversations(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "conversation.conversation",
            "view_mode": "list,form",
            "domain": [("calendar_event_id", "=", self.id)],
            "context": {
                "default_calendar_event_id": self.id,
                "default_kind": "meeting",
            },
        }
