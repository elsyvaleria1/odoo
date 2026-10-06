from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sms.tools.sms_api import ERROR_MESSAGES, SmsApi


class WizardIapAccountSendSmsCode(models.TransientModel):
    _name = "wizard.iap.account.send.sms.code"
    _description = "SMS Account Registration Phone Number Wizard"

    account_id = fields.Many2one(
        comodel_name="iap.account",
        required=True,
    )
    phone_number = fields.Char(required=True)

    def action_send_verification_code(self) -> dict:
        status = SmsApi(self.env, self.account_id)._send_verification_sms(
            self.phone_number
        )["state"]
        if status != "success":
            raise ValidationError(
                ERROR_MESSAGES.get(status, ERROR_MESSAGES["unknown_error"])
            )

        return {
            "type": "ir.actions.act_window",
            "target": "new",
            "name": self.env._("Register Account"),
            "view_mode": "form",
            "res_model": "wizard.iap.account.register.sms",
            "context": {"default_account_id": self.account_id.id},
        }
