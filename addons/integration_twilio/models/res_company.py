from odoo import fields, models

from odoo.addons.integration_twilio.tools.sms_api import SmsApiTwilio
from odoo.addons.phone_validation.tools import phone_validation


class ResCompany(models.Model):
    _inherit = "res.company"

    integration_twilio_config_id = fields.Many2one(
        comodel_name="integration.twilio.config",
        compute="_compute_integration_twilio_config_id",
        search="_search_integration_twilio_config_id",
    )
    # the company's own Twilio numbers, whose inverse names the company: a
    # collection it owns, not a setting the configuration keeps
    twilio_number_ids = fields.One2many(
        comodel_name="integration.twilio.number",
        inverse_name="company_id",
        string="Twilio Numbers",
    )

    def _search_integration_twilio_config_id(self, operator, value):
        return self._search_config_link("integration.twilio.config", operator, value)

    def _compute_integration_twilio_config_id(self) -> None:
        self._compute_config_link("integration_twilio_config_id")

    def _is_sms_sent_through_twilio(self) -> bool:
        self.check_singleton()
        return self.integration_twilio_config_id.sms_provider == "twilio"

    def _get_sms_api_class(self):
        if self._is_sms_sent_through_twilio():
            return SmsApiTwilio
        return super()._get_sms_api_class()

    def _get_twilio_sender(self, to_number):
        # an automated SMS: a conversation's reply names its own number
        senders = self.twilio_number_ids.filtered(
            lambda number: number.is_sms_capable and not number.is_conversation_only
        )
        country_code = phone_validation.phone_get_country_code_for_number(to_number)
        if not senders or not country_code:
            return senders[:1]
        return senders.sorted(
            lambda number: number.country_code == country_code, reverse=True
        )[:1]

    def _action_view_integration_twilio_config(self) -> dict:
        return {
            "name": self.env._("Manage Twilio Account"),
            "res_model": "wizard.integration.twilio.config.update",
            "res_id": False,
            "context": self.env.context,
            "type": "ir.actions.act_window",
            "views": [(False, "form")],
            "view_mode": "form",
            "target": "new",
        }
