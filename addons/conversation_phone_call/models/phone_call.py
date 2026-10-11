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
        call = self._filing_conversation()
        if not call.conversation_id:
            call.conversation_id = call._create_conversation()
        return call.conversation_id

    def _filing_conversation(self):
        return self.with_privilege(
            "conversation_phone_call.privilege_file_call_conversation",
            reason="a recorded call is filed on its conversation",
        )

    def _conversation_name(self) -> str:
        self.check_singleton()
        who = self.partner_id.name or self.contact_name or self.phone_number
        return self.env._("Call with %s", who or self.env._("unknown number"))

    def _create_conversation(self):
        self.check_singleton()
        partner = self.partner_id
        user = self.user_id
        return (
            self._filing_conversation()
            .env["conversation.conversation"]
            .with_context(mail_auto_subscribe_no_notify=True)
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
        for call in self._filing_conversation().filtered("conversation_id"):
            conversation = call.conversation_id
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
            conversation.with_context(mail_auto_subscribe_no_notify=True).write(vals)
            for attachment in conversation.segment_ids.attachment_id.filtered(
                lambda recording: recording.transcript_state == "done"
            ):
                conversation._name_call_voices(attachment)
        super()._on_call_details_completed()

    def _on_merged_into(self, call) -> None:
        conversation = self.conversation_id
        super()._on_merged_into(call)
        if conversation and not conversation.segment_ids:
            conversation.unlink()
