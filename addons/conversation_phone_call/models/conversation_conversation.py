from odoo import fields, models

DIRECTION_WORDS = {"incoming": "entrante", "outgoing": "saliente"}
CHANNEL_WORDS = {
    "softphone": "del conmutador",
    "pbx": "del conmutador",
    "mobile": "del teléfono de la empresa",
}


class ConversationConversation(models.Model):
    _inherit = "conversation.conversation"

    source = fields.Selection(
        selection_add=[("voip", "Phone system")],
        ondelete={"voip": "set default"},
    )
    phone_call_id = fields.Many2one(
        comodel_name="phone.call",
        string="Phone call",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )

    def _extra_preamble(self):
        preamble = super()._extra_preamble()
        call = self.phone_call_id
        if not call:
            return preamble
        lines = []
        direction = DIRECTION_WORDS.get(call.direction)
        channel = CHANNEL_WORDS.get(call.channel, "")
        number = call.phone_number
        if direction and number:
            lines.append(f"Llamada {direction} {channel}, con el número {number}.")
        elif number:
            lines.append(f"Llamada {channel}, con el número {number}.")
        if call.contact_name and not call.partner_id:
            lines.append(
                f"Contacto según el teléfono: {call.contact_name}. El teléfono nombra "
                "la llamada con el contacto: ese suele ser el nombre completo de la "
                "otra persona."
            )
        lines.extend(
            f"Archivo de la grabación: {name}."
            for name in self.segment_ids.attachment_id.mapped("name")
            if name
        )
        return "\n".join(part for part in (preamble, *lines) if part)

    def _on_media_transcribed(self, attachment) -> None:
        # before the parent adds the named voices to the attendees
        self._name_call_voices(attachment)
        super()._on_media_transcribed(attachment)

    def _name_call_voices(self, attachment) -> None:
        """Name the two voices of a two-party call: the phone's user and the
        call's contact. Whoever answers speaks first, so the direction says
        which voice is which; any other recording stays anonymous."""
        self.check_singleton()
        call = self.phone_call_id
        owner = call.user_id.partner_id
        contact = call.partner_id
        answerer = {"outgoing": contact, "incoming": owner}.get(call.direction)
        if not answerer or not owner or not contact or owner == contact:
            return
        # in this conversation's environment: the transcript's owner is
        # reached elevated, as is the call whose entry completes it
        voices = attachment.with_env(self.env).speaker_ids.filtered("turns")
        if len(voices) != 2 or voices.partner_id:
            return
        first, second = voices.sorted("first_spoke_s")
        first.partner_id = answerer
        second.partner_id = (owner | contact) - answerer
