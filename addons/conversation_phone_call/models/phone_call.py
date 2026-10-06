from odoo import fields, models

SOURCE_BY_CHANNEL = {"mobile": "mobile"}


class PhoneCall(models.Model):
    _inherit = "phone.call"

    conversation_id = fields.Many2one(
        comodel_name="conversation.conversation",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )

    def _recording_timeline(self):
        self.check_singleton()
        if not self.conversation_id:
            self.sudo().conversation_id = self._create_conversation()
        return self.conversation_id

    def _conversation_name(self) -> str:
        self.check_singleton()
        who = self.partner_id.name or self.contact_name or self.phone_number
        return self.env._("Call with %s", who or self.env._("unknown number"))

    def _create_conversation(self):
        self.check_singleton()
        partner = self.partner_id
        user = self.user_id
        return (
            self.env["conversation.conversation"]
            .sudo()
            .create(
                {
                    "name": self._conversation_name(),
                    "kind": "call",
                    "source": SOURCE_BY_CHANNEL.get(self.channel, "voip"),
                    "company_id": self.company_id.id,
                    "partner_id": partner.id,
                    "user_id": user.id,
                    "start": self.start_date or self.create_date,
                    "phone_call_id": self.id,
                    "attendee_ids": [
                        fields.Command.set((user.partner_id | partner).ids)
                    ],
                }
            )
        )

    def _on_call_details_completed(self) -> None:
        # the entry may name another company's line and the extension that
        # answered: the conversation, transcript and analysis follow the call
        # to the people who took it
        for call in self.filtered("conversation_id"):
            conversation = call.conversation_id.sudo()
            vals = {
                "name": call._conversation_name(),
                "company_id": call.company_id.id,
            }
            attendees = call.partner_id | call.user_id.partner_id
            if attendees:
                vals["attendee_ids"] = [
                    fields.Command.link(partner.id) for partner in attendees
                ]
            if call.partner_id and not conversation.partner_id:
                vals["partner_id"] = call.partner_id.id
            if call.user_id and call.user_id != conversation.user_id:
                vals["user_id"] = call.user_id.id
            conversation.write(vals)
        super()._on_call_details_completed()

    def _on_merged_into(self, call) -> None:
        conversation = self.conversation_id
        super()._on_merged_into(call)
        if conversation and not conversation.segment_ids:
            conversation.unlink()
