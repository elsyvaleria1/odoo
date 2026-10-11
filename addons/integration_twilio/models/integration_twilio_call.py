import logging
from datetime import UTC, timedelta
from email.utils import parsedate_to_datetime

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.integration.tools import CommError
from odoo.addons.phone_call.models.phone_call import number_key

_logger = logging.getLogger(__name__)

TRUNK_DIRECTIONS = {
    "trunking-originating": "incoming",
    "trunking-terminating": "outgoing",
}
FINAL_STATUSES = {"completed", "busy", "failed", "no-answer", "canceled"}
MATCH_WINDOW = timedelta(seconds=120)
REPORT_GRACE = timedelta(hours=2)
SYNC_OVERLAP = timedelta(days=1)
WITHHELD_CALLERS = {"+266696687"}


def _parse_twilio_date(value):
    if not value:
        return False
    return parsedate_to_datetime(value).astimezone(UTC).replace(tzinfo=None)


def _is_withheld(number: str) -> bool:
    return number in WITHHELD_CALLERS or not any(char.isdigit() for char in number)


def _sip_user(value: str) -> str:
    value = (value or "").removeprefix("sips:").removeprefix("sip:")
    return value.split("@", 1)[0]


class IntegrationTwilioCall(models.Model):
    _name = "integration.twilio.call"
    _description = "Twilio SIP Trunk Call"
    _order = "start_date desc, id desc"
    _check_company_auto = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    twilio_sid = fields.Char(
        string="Twilio Call SID",
        readonly=True,
        required=True,
    )
    trunk_sid = fields.Char(
        string="Trunk SID",
        readonly=True,
    )
    direction = fields.Selection(
        selection=[
            ("incoming", "Incoming"),
            ("outgoing", "Outgoing"),
        ],
        readonly=True,
        required=True,
    )
    phone_number = fields.Char(
        readonly=True,
        help="The other party's number",
    )
    line_number = fields.Char(
        readonly=True,
        help="The company number the call came in on or went out from",
    )
    twilio_status = fields.Char(
        string="Twilio Status",
        readonly=True,
    )
    start_date = fields.Datetime(
        index=True,
        readonly=True,
    )
    end_date = fields.Datetime(readonly=True)
    duration = fields.Integer(
        string="Duration (s)",
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    amount_price = fields.Float(
        string="Price",
        digits=(16, 5),
        readonly=True,
        help="What Twilio charged for the call's connectivity, in the currency "
        "beside it: per-minute prices are fractions of a cent, which the "
        "currency's own rounding would lose",
    )
    phone_call_id = fields.Many2one(
        comodel_name="phone.call",
        string="Reported Call",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
        help="The call the phone system reported to Odoo for this carrier record",
    )
    report_state = fields.Selection(
        selection=[
            ("pending", "Awaiting the phone system"),
            ("matched", "Reported"),
            ("unreported", "Never reported"),
            ("not_expected", "Not connected"),
        ],
        string="Report",
        default="pending",
        index=True,
        readonly=True,
        required=True,
        help="Whether the phone system reported this call to Odoo: a completed "
        "carrier call still unreported two hours after it ended was lost "
        "between the carrier and Odoo.",
    )

    _twilio_sid_unique = models.UniqueIndex(
        "(company_id, twilio_sid)",
        "A Twilio call is recorded once per company.",
    )

    @api.model
    def _cron_sync_trunk_calls(self) -> None:
        calls = self.sudo()
        configs = calls.env["integration.twilio.config"].search(
            [("credential_id", "!=", False)]
        )
        for config in configs:
            try:
                calls._sync_trunk_calls(config)
            except CommError as error:
                _logger.warning(
                    "Twilio: %s's trunk calls were not read: %s",
                    config.company_id.display_name,
                    error,
                )
        calls.search([("report_state", "=", "pending")])._reconcile_with_reports()

    @api.model
    def _sync_trunk_calls(self, config) -> None:
        since = (
            config.date_twilio_calls_synced or fields.Datetime.now()
        ) - SYNC_OVERLAP
        client = config._get_twilio_client()
        started = fields.Datetime.now()
        entries = [
            entry
            for entry in client.iterate(
                "Calls", "calls", params={"StartTime>": since.date().isoformat()}
            )
            if entry.get("direction") in TRUNK_DIRECTIONS
            and entry.get("status") in FINAL_STATUSES
        ]
        company = config.company_id
        known = self.search(
            [
                ("company_id", "=", company.id),
                ("twilio_sid", "in", [entry["sid"] for entry in entries]),
            ]
        ).grouped("twilio_sid")
        currencies = {
            currency.name: currency
            for currency in self.env["res.currency"]
            .with_context(active_test=False)
            .search(
                [("name", "in", list({entry.get("price_unit") for entry in entries}))]
            )
        }
        create_vals = []
        for entry in entries:
            vals = self._prepare_call_vals(entry, currencies)
            if record := known.get(entry["sid"]):
                record.write(vals)
            else:
                create_vals.append({**vals, "company_id": company.id})
        self.create(create_vals)
        config.date_twilio_calls_synced = started

    @api.model
    def _prepare_call_vals(self, entry, currencies) -> dict:
        direction = TRUNK_DIRECTIONS[entry["direction"]]
        caller, called = _sip_user(entry.get("from")), _sip_user(entry.get("to"))
        price = entry.get("price")
        currency = currencies.get(entry.get("price_unit"))
        other_party = caller if direction == "incoming" else called
        return {
            "twilio_sid": entry["sid"],
            "trunk_sid": entry.get("trunk_sid"),
            "direction": direction,
            "phone_number": False if _is_withheld(other_party) else other_party,
            "line_number": called if direction == "incoming" else caller,
            "twilio_status": entry.get("status"),
            "start_date": _parse_twilio_date(entry.get("start_time")),
            "end_date": _parse_twilio_date(entry.get("end_time")),
            "duration": int(entry.get("duration") or 0),
            "currency_id": currency.id if currency else False,
            "amount_price": abs(float(price)) if price else 0.0,
        }

    def _reconcile_with_reports(self) -> None:
        claimed = set(self.search([("phone_call_id", "!=", False)]).phone_call_id.ids)
        now = fields.Datetime.now()
        for record in self.sorted("start_date"):
            report = record._find_reported_call(claimed)
            if report:
                claimed.add(report.id)
                record.write({"phone_call_id": report.id, "report_state": "matched"})
            elif record.end_date and record.end_date + REPORT_GRACE <= now:
                record.report_state = (
                    "unreported" if record._is_report_expected() else "not_expected"
                )

    def _is_report_expected(self) -> bool:
        self.check_singleton()
        return self.direction == "incoming" or self.twilio_status == "completed"

    def _find_reported_call(self, claimed):
        self.check_singleton()
        key = number_key(self.phone_number)
        if not self.start_date:
            return self.env["phone.call"]
        candidates = self.env["phone.call"].search(
            Domain("company_id", "=", self.company_id.id)
            & Domain("channel", "=", "pbx")
            & Domain("direction", "=", self.direction)
            & Domain("start_date", ">=", self.start_date - MATCH_WINDOW)
            & Domain("start_date", "<=", self.start_date + MATCH_WINDOW)
            & Domain("id", "not in", list(claimed))
        )
        candidates = candidates.filtered(
            lambda call: number_key(call.phone_number) == key
        )
        return min(
            candidates,
            key=lambda call: abs(call.start_date - self.start_date),
            default=self.env["phone.call"],
        )
