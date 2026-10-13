import logging

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ExchangeChannel(models.Model):
    _name = "exchange.channel"
    _description = "Exchange Channel"
    _inherits = {"integration.service": "endpoint_id"}
    _order = "sequence, name"

    endpoint_id = fields.Many2one(
        comodel_name="integration.service",
        index=True,
        required=True,
        ondelete="cascade",
        help="Auth, rate limiting, retry policy, caching and TLS live on the "
        "endpoint. A channel adds only what the counterparty decides.",
    )

    protocol = fields.Selection(
        selection="_selection_protocol",
        index=True,
        required=True,
    )
    counterparty = fields.Selection(
        selection=[
            ("authority", "Tax or regulatory authority"),
            ("partner", "Trading partner"),
            ("agent", "Licensed agent or access point"),
        ],
        default="authority",
        index=True,
        required=True,
        help="The three things 'EDI' names -- fiscal clearance, partner "
        "interchange, document import -- on the record rather than in a "
        "module name. Only 'partner' is interchange in the strict sense.",
    )

    certificate_id = fields.Many2one(
        comodel_name="certificate.certificate",
        ondelete="restrict",
        help="Signing material this counterparty requires. Shared with every "
        "other consumer of certificate.certificate rather than re-uploaded.",
    )
    participant = fields.Char(
        help="Our identifier at the counterparty -- a Peppol participant id, "
        "an issuer RFC, a taxpayer number."
    )

    annul_window_days = fields.Integer(
        default=0,
        help="Days after acceptance during which an annulment is still "
        "admissible. Zero means the counterparty sets no window.",
    )
    reconcile_window_days = fields.Integer(
        default=2,
        help="Days a document the counterparty's answer did not name is still "
        "looked for at the counterparty. When they run out, the transmission "
        "expires and the document's owner is asked to check by hand.",
    )
    is_chained = fields.Boolean(
        help="The counterparty requires each document to reference the "
        "previous one, so transmissions on this channel form a chain."
    )
    is_inbox_enabled = fields.Boolean(
        default=False,
        help="The counterparty holds documents addressed to us that must be "
        "polled for. Off for a send-only channel.",
    )
    date_last_inbox = fields.Datetime(readonly=True)

    transmission_ids = fields.One2many(
        comodel_name="exchange.transmission",
        inverse_name="channel_id",
    )
    count_transmission = fields.Integer(compute="_compute_transmission_counts")
    count_transmission_open = fields.Integer(compute="_compute_transmission_counts")

    @api.model
    def _selection_protocol(self) -> list[tuple[str, str]]:
        return self.env["exchange.protocol"]._selection_protocol()

    @api.constrains("protocol", "company_id", "endpoint_id", "active")
    def _check_protocol_is_unique_per_company(self) -> None:
        for channel in self.filtered("active"):
            duplicate = self.search(  # noqa: E8507 -- one probe per channel, on its own protocol and company
                [
                    ("id", "!=", channel.id),
                    ("protocol", "=", channel.protocol),
                    ("company_id", "=", channel.company_id.id),
                    ("environment", "=", channel.environment),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    self.env._(
                        "%(company)s already reaches %(protocol)s through "
                        "channel %(name)s in this environment.",
                        company=channel.company_id.display_name,
                        protocol=channel.protocol,
                        name=duplicate.display_name,
                    ),
                )

    @api.constrains("protocol")
    def _check_protocol(self) -> None:
        known = self.env["exchange.protocol"]._get_protocols()
        for channel in self:
            if channel.protocol not in known:
                raise ValidationError(
                    self.env._(
                        "No installed module declares the exchange protocol "
                        "%(protocol)s.",
                        protocol=channel.protocol,
                    ),
                )

    @api.constrains("annul_window_days")
    def _check_annul_window_days(self) -> None:
        for channel in self:
            if channel.annul_window_days < 0:
                raise ValidationError(
                    self.env._("An annulment window cannot be negative."),
                )

    @api.constrains("reconcile_window_days")
    def _check_reconcile_window_days(self) -> None:
        for channel in self:
            if channel.reconcile_window_days < 0:
                raise ValidationError(
                    self.env._("A reconciliation window cannot be negative."),
                )

    def _compute_transmission_counts(self) -> None:
        totals = dict(
            self.env["exchange.transmission"]._read_group(
                domain=[("channel_id", "in", self.ids)],
                groupby=["channel_id"],
                aggregates=["__count"],
            )
        )
        open_totals = dict(
            self.env["exchange.transmission"]._read_group(
                domain=[
                    ("channel_id", "in", self.ids),
                    ("state", "in", ("draft", "queued", "sent")),
                ],
                groupby=["channel_id"],
                aggregates=["__count"],
            )
        )
        for channel in self:
            channel.count_transmission = totals.get(channel, 0)
            channel.count_transmission_open = open_totals.get(channel, 0)

    def action_view_transmissions(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Transmissions"),
            "res_model": "exchange.transmission",
            "view_mode": "list,form",
            "domain": [("channel_id", "=", self.id)],
            "context": {"default_channel_id": self.id},
        }

    def action_test_connection(self) -> dict:
        self.check_singleton()
        return self.endpoint_id.action_test_connection()

    def action_read_inbox(self) -> None:
        self.check_singleton()
        if not self.is_inbox_enabled:
            raise UserError(
                self.env._("Channel %(name)s holds no inbox to read.", name=self.name),
            )
        self._read_inbox()

    def is_retry_required(self, attempt_number: int) -> bool:
        self.check_singleton()
        return self.endpoint_id.is_retry_required(attempt_number)

    def get_retry_delay(self, attempt_number: int) -> int:
        self.check_singleton()
        return self.endpoint_id.get_retry_delay(attempt_number)

    def _enqueue_send(self) -> None:
        for channel in self:
            channel.delayed(
                identity_key=f"exchange.send:{channel.id}",
                channel=f"exchange.{channel.protocol}",
                name=f"Send queued transmissions over {channel.display_name}",
            )._job_send_queued()

    @api.job(channel="exchange", max_retries=0, trailing_run=True)
    def _job_send_queued(self) -> None:
        self.check_singleton()
        self.env["exchange.transmission"].search(
            [
                ("channel_id", "=", self.id),
                *self.env["exchange.transmission"]._get_due_domain(),
            ],
        )._send_many()

    def _get_api_client(self, credential=None):
        self.check_singleton()
        return self.endpoint_id._get_api_client(credential=credential)

    def _get_protocol(self):
        self.check_singleton()
        return self.env["exchange.protocol"]._get_protocol(self.protocol)

    def _read_inbox(self) -> None:
        for channel in self:
            protocol = channel._get_protocol()
            documents = protocol._read_inbox(channel)
            if documents:
                protocol._add_from_inbox(channel, documents)
            channel.sudo().date_last_inbox = fields.Datetime.now()

    @api.model
    def _cron_read_inboxes(self, limit: int = 20) -> None:
        channels = self.search(
            [("is_inbox_enabled", "=", True), ("active", "=", True)],
            order="date_last_inbox asc nulls first",
            limit=limit,
        )
        for channel in channels:
            try:
                with self.env.cr.savepoint():
                    channel._read_inbox()
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception:
                _logger.exception(
                    "Reading the inbox of channel %s failed", channel.display_name
                )
