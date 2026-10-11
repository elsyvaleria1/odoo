import logging
import re
from collections import defaultdict

from werkzeug.exceptions import NotFound

from odoo import api, fields, models

from odoo.addons.integration.tools.admission import Resolution
from odoo.addons.integration_twilio.tools.sms_api import SmsApiTwilio

_logger = logging.getLogger(__name__)

UUID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class SmsSms(models.Model):
    _inherit = "sms.sms"

    twilio_message_sid = fields.Char(
        related="sms_tracker_id.twilio_message_sid",
        depends=["sms_tracker_id"],
    )
    twilio_sender_id = fields.Many2one(
        comodel_name="integration.twilio.number",
        string="Twilio Sender",
        index="btree_not_null",
        ondelete="set null",
        help="The number this SMS must be sent from, whatever the recipient's "
        "country: the number a conversation's reply answers on.",
    )
    record_company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        ondelete="set null",
    )
    failure_type = fields.Selection(
        selection_add=[
            ("twilio_authentication", "Authentication Error"),
            ("twilio_callback", "Incorrect callback URL"),
            ("twilio_from_missing", "Missing From Number"),
            ("twilio_from_to", "From / To identic"),
        ]
    )

    @api.model
    def _receiver_for_twilio_status(self, uuid=None, **path_args) -> Resolution:
        if not uuid or not UUID_PATTERN.match(uuid):
            _logger.warning("Twilio SMS: status callback for a malformed uuid %r", uuid)
            raise NotFound
        subject = self.search([("uuid", "=", uuid)], limit=1)
        if subject:
            company = subject._get_sms_company()
        else:
            subject = self.env["sms.tracker"].search([("sms_uuid", "=", uuid)], limit=1)
            company = subject.twilio_company_id
        if not company:
            _logger.warning("Twilio SMS: status callback for no SMS (uuid %s)", uuid)
            raise NotFound
        return company.integration_twilio_config_id._prepare_twilio_resolution(
            subject,
            "twilio_sms_status",
            self.env._("%(company)s Twilio SMS status callbacks", company=company.name),
        )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["record_company_id"] = (
                vals.get("record_company_id") or self.env.company.id
            )
        return super().create(vals_list)

    def _split_by_api(self):
        batches = defaultdict(self.browse)
        through_iap = self.browse()
        for sms in self:
            company = sms._get_sms_company()
            if sms.twilio_sender_id or company._is_sms_sent_through_twilio():
                batches[company, sms.twilio_sender_id] += sms
            else:
                through_iap += sms
        for (company, sender), batch in batches.items():
            sms_api = SmsApiTwilio(self.env)
            sms_api._set_company(company)
            sms_api._set_sender(sender)
            yield sms_api, batch
        if through_iap:
            yield from super(SmsSms, through_iap)._split_by_api()

    def _get_sms_company(self):
        return (
            self.twilio_sender_id.company_id
            or self.mail_message_id.record_company_id
            or self.record_company_id
            or super()._get_sms_company()
        )

    def _get_send_batch_size(self):
        companies = self._get_sms_company()
        if any(company._is_sms_sent_through_twilio() for company in companies):
            return self.env["ir.config_parameter"]._get_positive_int_param(
                "integration_twilio.session.batch.size", 10
            )
        return super()._get_send_batch_size()

    def _handle_call_result_hook(self, results):
        twilio_sms = self.filtered(
            lambda sms: (
                sms.twilio_sender_id
                or sms._get_sms_company()._is_sms_sent_through_twilio()
            )
        )
        sms_by_uuid = twilio_sms.grouped("uuid")
        opted_out = []
        for result in results:
            sms = sms_by_uuid.get(result.get("uuid"))
            if not sms:
                continue
            if sms.sms_tracker_id and result.get("twilio_message_sid"):
                sms.sms_tracker_id.write(
                    {
                        "twilio_message_sid": result["twilio_message_sid"],
                        "twilio_company_id": sms._get_sms_company().id,
                    }
                )
            if result.get("failure_type") == "twilio_opted_out":
                opted_out.append(sms.number)
        if opted_out:
            self.env["phone.blacklist"]._add(
                opted_out,
                message=self.env._(
                    "Twilio refused to send: the recipient replied STOP"
                ),
            )
        super(SmsSms, self - twilio_sms)._handle_call_result_hook(results)
