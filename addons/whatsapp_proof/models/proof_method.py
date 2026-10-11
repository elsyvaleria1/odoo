import re

from odoo import fields, models

PHONE_FIELD = "phone_ids"
_VARIABLE_SPACING = re.compile(r"\s*[\r\n\t]+\s*| {4,}")
ANSWERS = ("confirmed", "disputed")


class ProofMethod(models.Model):
    _inherit = "proof.method"

    code = fields.Selection(
        selection_add=[("whatsapp_confirm", "WhatsApp Confirmation")],
        ondelete={"whatsapp_confirm": "cascade"},
    )
    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="WhatsApp Template",
        domain="[('model', '=', 'proof.delivery'), ('status', '=', 'approved')]",
        ondelete="set null",
        help="The approved template the question goes out as: a utility template "
        "on model Proof Confirmation Message, phone field partner_id.phone_ids, "
        "the company as its first free-text variable and "
        "what the contact confirms as its second, then two quick replies, the "
        "first confirming and the second saying it is not right.",
    )

    def _is_enrolled_contact(self, partner: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code == "whatsapp_confirm":
            return bool(self._get_wa_template() and self._get_whatsapp_number(partner))
        return super()._is_enrolled_contact(partner)

    def _get_wa_template(self) -> models.BaseModel:
        template = self.wa_template_id
        if not template or not template.has_access("read"):
            return template.browse()
        replies = template.button_ids.filtered(
            lambda button: button.button_type == "quick_reply"
        )
        if template.status != "approved" or len(replies) < 2:
            return template.browse()
        return template

    def _get_whatsapp_number(self, partner: models.BaseModel) -> str | bool:
        return partner and partner._whatsapp_phone_format(fpath=PHONE_FIELD)

    def _deliver_confirmation(
        self, challenge: models.BaseModel, reminder: bool = False
    ) -> models.BaseModel:
        self.check_singleton()
        if self.code != "whatsapp_confirm":
            return super()._deliver_confirmation(challenge, reminder=reminder)
        template = self._get_wa_template()
        number = self._get_whatsapp_number(challenge.partner_id)
        if not template or not number:
            return self.env["proof.delivery"]
        delivery = self.env["proof.delivery"].create(
            {
                "challenge_id": challenge.id,
                "method_id": self.id,
                "sent_to": f"WhatsApp {'*' * max(len(number) - 4, 1)}{number[-4:]}",
                "address": number,
            }
        )
        summary = _VARIABLE_SPACING.sub(
            " ", "; ".join(f"{label}: {value}" for label, value in challenge.summary)
        )
        message = self.env["mail.message"].create(
            {
                "model": delivery._name,
                "res_id": delivery.id,
                "message_type": "whatsapp_message",
                "body": summary,
            }
        )
        whatsapp_message = self.env["whatsapp.message"].create(
            {
                "mail_message_id": message.id,
                "mobile_number": number,
                "mobile_number_formatted": number,
                "wa_template_id": template.id,
                "wa_account_id": template.wa_account_id.id,
                "free_text_json": {
                    "free_text_1": (
                        challenge.company_id or challenge.user_id.company_id
                    ).name,
                    "free_text_2": summary,
                },
            }
        )
        whatsapp_message._send(force_send_by_cron=True)
        delivery.ref = str(whatsapp_message.id)
        return delivery

    def _get_reply_verdict(self, whatsapp_message, message) -> str | None:
        buttons = whatsapp_message.wa_template_id.button_ids.filtered(
            lambda button: button.button_type == "quick_reply"
        ).sorted("sequence")[:2]
        pressed = (message.get("button") or {}).get("text")
        for button, verdict in zip(buttons, ANSWERS, strict=False):
            if button.name == pressed:
                return verdict
        return None
