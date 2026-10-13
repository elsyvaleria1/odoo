from odoo import Command, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_sent_message_on_sms(self, phone, _, basic_image=False) -> None:
        if not (
            self
            and self.config_id.module_pos_sms
            and self.config_id.sms_receipt_template_id
            and phone
        ):
            return
        self.check_singleton()
        sms_composer = (
            self.env["wizard.sms.sms.send"]
            .with_context(active_id=self.id)
            .create(
                {
                    "composition_mode": "comment",
                    "numbers": phone,
                    "recipient_single_number_itf": phone,
                    "template_id": self.config_id.sms_receipt_template_id.id,
                    "res_model": "pos.order",
                }
            )
        )
        self.phone_ids = [
            Command.link(
                self.env["phone.number"]
                .with_context(default_country_id=self.phone_country_id.id)
                .create({"number": phone, "type": "mobile"})
                .id
            )
        ]
        sms_composer.action_send_sms()
