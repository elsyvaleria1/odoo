import logging
import re
from urllib.parse import urljoin

from werkzeug.exceptions import NotFound

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.integration.tools import CommError
from odoo.addons.integration.tools.admission import Resolution
from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)

INBOUND_SMS_ROUTE = "/integration_twilio/sms/inbound/"
NUMBER_SID_PATTERN = re.compile(r"^PN[0-9a-fA-F]{32}$")
# Twilio waits 15 s for the answer: what the media may take is bounded
MAX_INBOUND_MEDIA = 3
MEDIA_TIMEOUT = (3, 4)
# Twilio's default opt-out keywords on long codes, applied by Twilio before
# the message reaches Odoo; Odoo mirrors them so it stops trying too
OPT_OUT_KEYWORDS = {
    "STOP",
    "STOPALL",
    "UNSUBSCRIBE",
    "CANCEL",
    "END",
    "QUIT",
    "REVOKE",
    "OPTOUT",
}
OPT_IN_KEYWORDS = {"START", "YES", "UNSTOP"}


class IntegrationTwilioNumber(models.Model):
    _name = "integration.twilio.number"
    _description = "Twilio Number"
    _order = "sequence, id"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index="btree",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=1)
    active = fields.Boolean(default=True)
    number = fields.Char(
        string="Twilio Number",
        required=True,
    )
    country_id = fields.Many2one(
        comodel_name="res.country",
        required=True,
    )
    country_code = fields.Char(
        related="country_id.code",
        string="Country Code",
    )
    twilio_sid = fields.Char(
        string="Twilio SID",
        copy=False,
        readonly=True,
        help="Twilio's own id for this number (PN...), set when it is synced "
        "from the account.",
    )
    is_sms_capable = fields.Boolean(
        string="SMS",
        default=True,
    )
    is_mms_capable = fields.Boolean(string="MMS")
    is_voice_capable = fields.Boolean(string="Voice")
    is_sms_routed = fields.Boolean(
        string="Receives SMS in Odoo",
        copy=False,
        readonly=True,
        help="Twilio sends this number's incoming SMS to Odoo, as last synced "
        "from the account.",
    )
    twilio_sms_url = fields.Char(
        string="Twilio SMS URL",
        copy=False,
        readonly=True,
        help="Where Twilio sends this number's incoming SMS, as it reported it: "
        "the URL its webhooks are signed for.",
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Answered By",
        domain="[('share', '=', False), ('company_ids', 'in', company_id)]",
        help="Who receives the SMS conversations started on this number.",
    )

    _twilio_sid_unique = models.UniqueIndex(
        "(company_id, twilio_sid) WHERE twilio_sid IS NOT NULL",
        "A Twilio number is synced once per company.",
    )

    @api.constrains("user_ids", "company_id")
    def _check_user_ids(self) -> None:
        for number in self:
            strangers = number.user_ids.filtered(
                lambda user, number=number: (
                    user.share or number.company_id not in user.company_ids
                )
            )
            if strangers:
                raise ValidationError(
                    self.env._(
                        "%(number)s is answered by internal users of %(company)s "
                        "only: %(users)s",
                        number=number.number,
                        company=number.company_id.name,
                        users=", ".join(strangers.mapped("name")),
                    )
                )

    def write(self, vals):
        result = super().write(vals)
        if "user_ids" in vals:
            self._sync_conversation_members()
        return result

    def _sync_conversation_members(self) -> None:
        # a conversation's members are the users its number names: who is
        # added sees the conversations already open, who is removed stops
        channels = self.env["discuss.channel"].search(
            [("channel_type", "=", "sms"), ("twilio_number_id", "in", self.ids)]
        )
        for channel in channels:
            wanted = channel.twilio_number_id.user_ids.partner_id
            if not wanted:
                continue
            members = channel.channel_member_ids
            leaving = members.filtered(
                lambda member, wanted=wanted: member.partner_id not in wanted
            )
            missing = wanted - (members - leaving).partner_id
            leaving.unlink()
            if missing:
                channel._add_members(partners=missing, post_joined_message=False)

    @api.depends("number", "country_id")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.number} ({record.country_id.name})"

    def _get_inbound_sms_url(self) -> str:
        # keyed on Twilio's own id, which a caller cannot count through
        self.check_singleton()
        return urljoin(
            self.company_id.get_base_url(), f"{INBOUND_SMS_ROUTE}{self.twilio_sid}"
        )

    @staticmethod
    def _number_digits(number) -> str:
        return "".join(char for char in number or "" if char.isdigit())

    @api.model
    def _sync_from_account(self, company) -> None:
        # numbers synced before and gone from the account are archived, as a
        # conversation still names them; numbers typed in by hand, which
        # Twilio never named, stay
        client = company.integration_twilio_config_id._get_twilio_client()
        reported = list(
            client.iterate("IncomingPhoneNumbers", "incoming_phone_numbers")
        )
        numbers = self.with_context(active_test=False).search(
            [("company_id", "=", company.id)]
        )
        by_sid = {number.twilio_sid: number for number in numbers if number.twilio_sid}
        by_number = {
            self._number_digits(number.number): number
            for number in numbers
            if not number.twilio_sid
        }
        country_codes = {
            phone_validation.phone_get_country_code_for_number(entry["phone_number"])
            for entry in reported
        }
        countries = {
            country.code: country
            for country in self.env["res.country"].search(
                [("code", "in", [code for code in country_codes if code])]
            )
        }
        kept = self.browse()
        for entry in reported:
            capabilities = entry.get("capabilities") or {}
            number = by_sid.get(entry["sid"]) or by_number.get(
                self._number_digits(entry["phone_number"])
            )
            country = countries.get(
                phone_validation.phone_get_country_code_for_number(
                    entry["phone_number"]
                )
            )
            vals = {
                "active": True,
                "twilio_sid": entry["sid"],
                "twilio_sms_url": entry.get("sms_url") or False,
                "number": entry["phone_number"],
                "is_sms_capable": bool(capabilities.get("sms")),
                "is_mms_capable": bool(capabilities.get("mms")),
                "is_voice_capable": bool(capabilities.get("voice")),
            }
            if country:
                vals["country_id"] = country.id
            if number:
                number.write(vals)
            elif country:
                number = self.create(
                    {
                        **vals,
                        "company_id": company.id,
                        "user_ids": [Command.set([self.env.uid])],
                    }
                )
            else:
                continue
            # an SMS application on the number overrides its SMS URL
            number.is_sms_routed = (
                not entry.get("sms_application_sid")
                and entry.get("sms_url") == number._get_inbound_sms_url()
            )
            kept |= number
        (numbers.filtered("twilio_sid") - kept).active = False

    def _route_sms_to_odoo(self):
        routed = self.filtered(
            lambda number: number.twilio_sid and number.is_sms_capable
        )
        for company, numbers in routed.grouped("company_id").items():
            client = company.integration_twilio_config_id._get_twilio_client()
            for number in numbers:
                client.call(
                    "POST",
                    f"IncomingPhoneNumbers/{number.twilio_sid}",
                    data={
                        "SmsUrl": number._get_inbound_sms_url(),
                        "SmsMethod": "POST",
                        "SmsApplicationSid": "",
                    },
                )
                number.write(
                    {
                        "is_sms_routed": True,
                        "twilio_sms_url": number._get_inbound_sms_url(),
                    }
                )
        return routed

    @api.model
    def _receiver_for_inbound_sms(self, twilio_sid=None, **path_args) -> Resolution:
        if not twilio_sid or not NUMBER_SID_PATTERN.match(twilio_sid):
            raise NotFound
        number = self.search([("twilio_sid", "=", twilio_sid)], limit=1)
        if not number:
            raise NotFound
        company = number.company_id
        return company.integration_twilio_config_id._prepare_twilio_resolution(
            number,
            "twilio_sms_inbound",
            self.env._("%(company)s Twilio incoming SMS", company=company.name),
            signed_urls=[number.twilio_sms_url] if number.twilio_sms_url else [],
        )

    def _receive_sms(self, params) -> None:
        self.check_singleton()
        sender = params.get("From")
        if not sender:
            return
        channel = self.env["discuss.channel"]._get_sms_channel(self, sender)
        partner = channel.sms_partner_id
        channel.message_post(
            body=params.get("Body") or "",
            author_id=partner.id or False,
            email_from=False if partner else sender,
            message_type="sms",
            subtype_xmlid="mail.mt_comment",
            attachments=self._download_inbound_media(params),
        )
        self._apply_opt_out(sender, params.get("OptOutType"), params.get("Body"))

    def _download_inbound_media(self, params) -> list[tuple]:
        try:
            count = min(int(params.get("NumMedia") or 0), MAX_INBOUND_MEDIA)
        except ValueError:
            return []
        if not count:
            return []
        client = self.company_id.integration_twilio_config_id._get_twilio_client()
        attachments = []
        for index in range(count):
            url = params.get(f"MediaUrl{index}")
            if not url:
                continue
            try:
                response = client.download(url, timeout=MEDIA_TIMEOUT)
            except CommError as error:
                _logger.warning(
                    "Twilio: media %s of an incoming SMS was not fetched: %s",
                    index,
                    error,
                )
                continue
            content_type = params.get(
                f"MediaContentType{index}"
            ) or response.headers.get("Content-Type")
            attachments.append(
                (f"media-{index}", response.content, {"mimetype": content_type})
            )
        return attachments

    def _apply_opt_out(self, sender, opt_out_type, body) -> None:
        # Advanced Opt-Out names the keyword it acted on; without it, the
        # message is the keyword alone, as Twilio's default handling reads it
        keyword = (body or "").strip().upper()
        if opt_out_type not in ("STOP", "START"):
            opt_out_type = (
                "STOP"
                if keyword in OPT_OUT_KEYWORDS
                else "START"
                if keyword in OPT_IN_KEYWORDS
                else None
            )
        if not opt_out_type:
            return
        sanitized = self.company_id.partner_id._phone_format(number=sender) or sender
        blacklist = self.env["phone.blacklist"]
        message = self.env._(
            "Replied %(keyword)s to %(number)s by SMS",
            keyword=opt_out_type,
            number=self.number,
        )
        if opt_out_type == "STOP":
            blacklist._add([sanitized], message=message)
        else:
            blacklist._remove([sanitized], message=message)

    def action_unlink(self) -> dict:
        # archived, not deleted: a conversation on it keeps its number
        self.active = False
        return self.company_id._action_view_integration_twilio_config()
