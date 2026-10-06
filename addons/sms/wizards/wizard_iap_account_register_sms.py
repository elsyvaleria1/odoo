from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sms.tools.sms_api import ERROR_MESSAGES, SmsApi


class WizardIapAccountRegisterSms(models.TransientModel):
    _name = "wizard.iap.account.register.sms"
    _description = "SMS Account Verification Code Wizard"

    account_id = fields.Many2one(
        comodel_name="iap.account",
        required=True,
    )
    verification_code = fields.Char(required=True)

    def action_register(self) -> dict:
        status = SmsApi(self.env, self.account_id)._confirm_account(
            self.verification_code
        )["state"]
        if status != "success":
            raise ValidationError(
                ERROR_MESSAGES.get(status, ERROR_MESSAGES["unknown_error"])
            )

        self.account_id.state = "registered"
        self.env["iap.account"]._send_success_notification(
            message=self.env._("Your SMS account has been successfully registered."),
        )

        sender_name_wizard = self.env["wizard.iap.account.update.sms.sender"].create(
            {
                "account_id": self.account_id.id,
            }
        )

        return {
            "type": "ir.actions.act_window",
            "target": "new",
            "name": self.env._("Choose your sender name"),
            "view_mode": "form",
            "res_model": "wizard.iap.account.update.sms.sender",
            "res_id": sender_name_wizard.id,
        }
