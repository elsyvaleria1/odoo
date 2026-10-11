import functools
import logging
import re
from urllib.parse import urljoin

from werkzeug.exceptions import NotFound
from werkzeug.wrappers import Response

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request

from odoo.addons.integration.tools import CommError
from odoo.addons.integration.tools.admission import Resolution
from odoo.addons.integration_twilio.tools.twilio_api import TwilioClient
from odoo.addons.integration_twilio.tools.twilio_signature import is_signature_valid

_logger = logging.getLogger(__name__)

ACCOUNT_SID_PATTERN = re.compile(r"^AC[0-9a-fA-F]{32}$")
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response/>'
IDEMPOTENCY_HEADER = "I-Twilio-Idempotency-Token"


class IntegrationTwilioConfig(models.Model):
    _name = "integration.twilio.config"
    _description = "A company's Twilio account"
    _inherit = [
        "mixin.company.config",
        "mixin.credential.holder",
        "mixin.mail.thread",
        "mixin.mail.activity",
    ]
    _credential_purpose = "integration_twilio:account"
    _CREDENTIAL_FIELDS = {
        "twilio_account_sid": "username",
        "twilio_auth_token": "password",
    }

    sms_provider = fields.Selection(
        selection=[
            ("iap", "Send via Odoo"),
            ("twilio", "Send via Twilio"),
        ],
        string="SMS Provider",
        default="iap",
    )
    credential_id = fields.Many2one(
        comodel_name="credential.credential",
        string="Credential",
        copy=False,
        ondelete="restrict",
        groups="base.group_system",
        help="The vault credential holding this company's Account SID and Auth "
        "Token, bound to the Twilio service so every call authenticates with it.",
    )
    twilio_account_sid = fields.Char(
        string="Account SID",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
    )
    twilio_auth_token = fields.Char(
        string="Auth Token",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_system",
        help="Authenticates the API calls and signs the webhooks Twilio sends.",
    )
    twilio_account_status = fields.Selection(
        selection=[
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("closed", "Closed"),
        ],
        string="Account Status",
        readonly=True,
        tracking=True,
    )
    twilio_account_type = fields.Selection(
        selection=[
            ("Trial", "Trial"),
            ("Full", "Full"),
        ],
        string="Account Type",
        readonly=True,
        tracking=True,
    )
    twilio_currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Balance Currency",
        readonly=True,
    )
    amount_twilio_balance = fields.Monetary(
        string="Balance",
        currency_field="twilio_currency_id",
        readonly=True,
    )
    amount_twilio_balance_alert = fields.Monetary(
        string="Alert Below",
        currency_field="twilio_currency_id",
        help="A balance under this amount makes an activity for whoever last "
        "updated the account; zero alerts on nothing but a suspended account.",
    )
    date_twilio_checked = fields.Datetime(
        string="Last Checked",
        readonly=True,
    )
    twilio_alert_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Alert User",
        domain="[('share', '=', False)]",
        help="Who is given an activity when the account is suspended or its "
        "balance falls under the alert amount; the administrator when empty.",
    )
    date_twilio_calls_synced = fields.Datetime(
        string="Trunk Calls Synced",
        readonly=True,
    )

    @api.depends("company_id")
    def _compute_display_name(self):
        for config in self:
            config.display_name = self.env._(
                "Twilio account of %(company)s", company=config.company_id.name
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_account_sid_format(vals.get("twilio_account_sid"))
        return super().create(vals_list)

    def write(self, vals):
        self._check_account_sid_format(vals.get("twilio_account_sid"))
        return super().write(vals)

    def _check_account_sid_format(self, account_sid) -> None:
        if account_sid and not ACCOUNT_SID_PATTERN.match(account_sid):
            raise ValidationError(
                self.env._(
                    "A Twilio Account SID is 'AC' followed by 32 hexadecimal characters."
                )
            )

    @api.model
    def _create_holding_credential(self, name, company_id, secrets):
        credential = super()._create_holding_credential(name, company_id, {})
        credential.write(
            {
                "endpoint_id": self.env.ref("integration_twilio.service_twilio").id,
                "category_id": self.env.ref(
                    "credential.credential_category_basic_auth"
                ).id,
                "auto_validate_health": True,
            }
        )
        if secrets:
            credential.write(secrets)
        return credential

    def _get_twilio_client(self) -> TwilioClient:
        return TwilioClient(self)

    def _prepare_twilio_resolution(self, subject, purpose, label, signed_urls=()):
        self.check_singleton()
        if not self._get_held_secret("username"):
            raise NotFound
        return Resolution(
            subject,
            gate=(self.company_id, label, purpose),
            verify=functools.partial(
                self._is_twilio_request_authentic, signed_urls=tuple(signed_urls)
            ),
            event_id=request.httprequest.headers.get(IDEMPOTENCY_HEADER),
        )

    def _is_twilio_request_authentic(self, headers, body, signed_urls=()) -> bool:
        self.check_singleton()
        httprequest = request.httprequest
        query = httprequest.query_string.decode()
        configured = urljoin(self.company_id.get_base_url(), httprequest.path)
        if query:
            configured = f"{configured}?{query}"
        authentic = is_signature_valid(
            self._get_held_secret("password"),
            [configured, *signed_urls],
            httprequest.form.items(multi=True),
            headers.get("X-Twilio-Signature"),
        )
        if not authentic:
            _logger.warning(
                "Twilio: refused a callback to %s whose signature does not match "
                "%s's account",
                httprequest.path,
                self.company_id.display_name,
            )
        return authentic

    @api.model
    def _prepare_twilio_refusal_response(self, refused):
        if refused.error_code == "duplicate_event":
            return Response(EMPTY_TWIML, status=200, content_type="text/xml")
        return request.prepare_json_response(
            {"error": refused.error_code}, status=refused.status
        )

    def _refresh_account_state(self) -> None:
        self.check_singleton()
        client = self._get_twilio_client()
        account = client.call("GET", client.account_url())
        balance = client.call("GET", "Balance")
        vals = {
            "twilio_account_status": account.get("status"),
            "twilio_account_type": account.get("type"),
            "date_twilio_checked": fields.Datetime.now(),
        }
        if "balance" in balance:
            currency = (
                self.env["res.currency"]
                .with_context(active_test=False)
                .search([("name", "=", balance.get("currency"))], limit=1)
            )
            vals |= {
                "twilio_currency_id": currency.id,
                "amount_twilio_balance": float(balance["balance"]),
            }
        self.write(vals)
        self._schedule_account_alerts()

    def _get_account_alerts(self) -> dict[str, bool]:
        self.check_singleton()
        low = (
            bool(self.twilio_currency_id)
            and self.amount_twilio_balance_alert > 0
            and self.amount_twilio_balance < self.amount_twilio_balance_alert
        )
        return {
            "integration_twilio.mail_activity_data_twilio_account_stopped": (
                self.twilio_account_status in ("suspended", "closed")
            ),
            "integration_twilio.mail_activity_data_twilio_balance_low": low,
        }

    def _schedule_account_alerts(self) -> None:
        for type_xmlid, raised in self._get_account_alerts().items():
            activity_type = self.env.ref(type_xmlid)
            existing = self.activity_ids.filtered(
                lambda activity, activity_type=activity_type: (
                    activity.activity_type_id == activity_type
                )
            )
            if raised and not existing:
                responsible = self._get_account_responsible()
                self.with_context(lang=responsible.lang).activity_schedule(
                    type_xmlid,
                    note=self.with_context(lang=responsible.lang).env._(
                        "%(company)s's Twilio account: status %(status)s, balance "
                        "%(balance)s %(currency)s. SMS and calls stop when the "
                        "account is suspended or out of funds.",
                        company=self.company_id.display_name,
                        status=self.twilio_account_status or "-",
                        balance=self.amount_twilio_balance,
                        currency=self.twilio_currency_id.name or "",
                    ),
                    user_id=responsible.id,
                )
            elif not raised and existing:
                existing.action_feedback(
                    feedback=self.env._("Cleared at the last check.")
                )

    def _get_account_responsible(self):
        self.check_singleton()
        return self.twilio_alert_user_id or self.env.ref("base.user_admin")

    def action_check_account(self) -> None:
        for config in self:
            try:
                config._refresh_account_state()
            except CommError as error:
                raise UserError(
                    self.env._("Twilio did not answer: %s", error.message)
                ) from error
