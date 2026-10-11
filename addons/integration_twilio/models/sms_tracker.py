from odoo import fields, models

TWILIO_CODE_TO_FAILURE_TYPE = {
    "30002": "expired",
    "30003": "not_delivered",
    "30004": "rejected",
    "30005": "invalid_destination",
    "30006": "not_allowed",
    "30007": "rejected",
    "30008": "not_delivered",
}


class SmsTracker(models.Model):
    _inherit = "sms.tracker"

    twilio_message_sid = fields.Char(
        string="Twilio Message SID",
        readonly=True,
    )
    twilio_company_id = fields.Many2one(
        comodel_name="res.company",
        string="Twilio Account Company",
        readonly=True,
        help="The company whose Twilio account sent the SMS and signs its "
        "status callbacks, kept after the SMS itself is deleted",
    )

    def _action_update_from_twilio_error(self, sms_status, error_code, error_message):
        failure_type = TWILIO_CODE_TO_FAILURE_TYPE.get(error_code) or (
            None if sms_status == "failed" else "not_delivered"
        )
        return self.with_context(
            sms_known_failure_reason=error_message
        )._action_update_from_provider_error(failure_type)
