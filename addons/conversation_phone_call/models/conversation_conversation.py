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
