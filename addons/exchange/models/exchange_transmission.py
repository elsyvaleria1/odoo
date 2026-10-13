import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from odoo import api, fields, models
from odoo.db import BaseCursor
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError, ValidationError
from odoo.tools import SQL, frozendict

from ..tools import SETTLED_STATES, NotDelivered, Verdict

_logger = logging.getLogger(__name__)

_OPEN_STATES = ("draft", "queued", "sent")

DISPATCH_LOCK_TIMEOUT = "5s"

_SUBJECT_HOOKS = {
    "settled": "_on_transmission_settled",
    "unresolved": "_on_transmission_unresolved",
}


class ExchangeTransmission(models.Model):
    _name = "exchange.transmission"
    _description = "Exchange Transmission"
    _order = "date_created desc, id desc"
    _rec_name = "display_name"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=True),
        }
    )

    subject_id = fields.Reference(
        selection="_selection_subject_models",
        index=True,
        required=True,
        help="The business record this transmission is about.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )

    channel_id = fields.Many2one(
        comodel_name="exchange.channel",
        index=True,
        required=True,
        ondelete="restrict",
    )
    protocol = fields.Selection(
        related="channel_id.protocol",
    )

    intent = fields.Selection(
        selection=[
            ("issue", "Issue"),
            ("annul", "Annul"),
            ("amend", "Amend"),
            ("query", "Query"),
        ],
        default="issue",
        index=True,
        required=True,
        help="What we are asking the counterparty for. Separate from state "
        "because an annulment that failed is intent=annul, state=rejected -- "
        "not a value in the issuing field.",
    )
    document_kind = fields.Selection(
        selection="_selection_document_kind",
        index=True,
        help="Which document this is, when a counterparty takes more than one "
        "about the same record -- an invoice and its expense classification, a "
        "CFDI and the payment complement. Not a phase and not an ask: the third "
        "axis l10n_mx_edi flattened into its sixteen-value state.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("queued", "Queued"),
            ("sent", "Sent"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("expired", "Expired"),
        ],
        default="draft",
        index=True,
        required=True,
        help="Where the ask has got to, as the counterparty sees it. Whether "
        "the call itself completed is on the event log, not here.",
    )
    is_settled = fields.Boolean(
        compute="_compute_is_settled",
        store=True,
        index=True,
    )

    date_created = fields.Datetime(
        default=fields.Datetime.now,
        index=True,
        readonly=True,
        required=True,
    )
    date_sent = fields.Datetime(readonly=True)
    date_settled = fields.Datetime(readonly=True)

    attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index="btree_not_null",
        ondelete="set null",
        help="What we sent, exactly as it went.",
    )
    response_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        index="btree_not_null",
        ondelete="set null",
        help="What came back, exactly as it arrived.",
    )
    reference = fields.Char(
        index=True,
        help="The counterparty's own identifier for this exchange, whatever "
        "it calls it -- uuid, mark, index, zip key, CSV.",
    )
    message = fields.Text(
        readonly=True,
        help="The counterparty's own words. Never paraphrased.",
    )

    parent_id = fields.Many2one(
        comodel_name="exchange.transmission",
        index=True,
        ondelete="cascade",
        help="The transmission this one acts upon: an annulment's issue, an "
        "amendment's original.",
    )
    chain_previous_id = fields.Many2one(
        comodel_name="exchange.transmission",
        index=True,
        ondelete="restrict",
        help="The previous link, for a counterparty that requires each "
        "document to reference the one before it.",
    )

    retry_count = fields.Integer(
        default=0,
        readonly=True,
    )
    dispatch_count = fields.Integer(
        default=0,
        readonly=True,
        help="How many times the document was handed to the counterparty with "
        "the outcome recorded. A hand-off logged beyond it never had its answer "
        "recorded: the document is not sent again, its outcome is unknown.",
    )
    date_next_retry = fields.Datetime(
        index=True,
        readonly=True,
    )
    date_last_polled = fields.Datetime(
        readonly=True,
        help="When the verdict cron last asked the counterparty about this "
        "transmission, whatever the answer. The cron asks the least recently "
        "asked first, so a backlog it cannot cover in one batch still rotates.",
    )
    date_reconcile_deadline = fields.Datetime(
        readonly=True,
        help="Set when whether the counterparty received this transmission "
        "is unknown: it answered without naming it, or the call carrying it "
        "failed after it may have arrived. Until then its verdict is read "
        "back from the counterparty; after it, the transmission expires.",
    )

    event_log_id = fields.Many2one(
        comodel_name="integration.exchange",
        index=True,
        ondelete="set null",
        help="The transport record: whether the call completed. A settled "
        "transmission whose call failed is a contradiction, and the "
        "constraint below says so.",
    )

    display_name = fields.Char(compute="_compute_display_name")

    _queue_idx = models.Index("(state, date_next_retry)")
    _poll_idx = models.Index("(state, date_last_polled ASC NULLS FIRST, id)")
    _subject_idx = models.Index("(subject_id, intent)")
    _reference_uniq = models.UniqueIndex(
        "(channel_id, reference, intent, document_kind) NULLS NOT DISTINCT "
        "WHERE reference IS NOT NULL",
        "A counterparty issues one reference per ask.",
    )

    @api.constrains("state", "event_log_id")
    def _check_state_agrees_with_transport(self) -> None:
        for transmission in self:
            log = transmission.event_log_id
            if not log:
                continue
            if transmission.state == "accepted" and log.state == "failed":
                raise ValidationError(
                    self.env._(
                        "Transmission %(name)s is accepted while the call that "
                        "carried it failed. One of the two readings is wrong.",
                        name=transmission.display_name,
                    ),
                )

    @api.constrains("parent_id")
    def _check_parent_id(self) -> None:
        for transmission in self:
            if transmission.parent_id and transmission.intent == "issue":
                raise ValidationError(
                    self.env._("An issuing transmission acts upon nothing."),
                )

    @api.constrains("document_kind", "channel_id")
    def _check_document_kind_belongs_to_the_protocol(self) -> None:
        for transmission in self:
            kind = transmission.document_kind
            if not kind:
                continue
            protocol, _, _rest = kind.partition(".")
            if protocol != transmission.protocol:
                raise ValidationError(
                    self.env._(
                        "%(kind)s is a document of the %(owner)s protocol, and "
                        "this transmission goes over %(protocol)s.",
                        kind=kind,
                        owner=protocol,
                        protocol=transmission.protocol,
                    ),
                )

    @api.constrains("chain_previous_id")
    def _check_chain_previous_id(self) -> None:
        for transmission in self:
            previous = transmission.chain_previous_id
            if previous and previous.channel_id != transmission.channel_id:
                raise ValidationError(
                    self.env._("A chain does not cross channels."),
                )

    @api.depends("state")
    def _compute_is_settled(self) -> None:
        for transmission in self:
            transmission.is_settled = transmission.state in SETTLED_STATES

    @api.depends("intent", "state", "channel_id.name", "reference")
    def _compute_display_name(self):
        intents = dict(self._fields["intent"]._description_selection(self.env))
        states = dict(self._fields["state"]._description_selection(self.env))
        for transmission in self:
            label = f"{intents.get(transmission.intent, '')} / {states.get(transmission.state, '')}"
            if transmission.reference:
                label = f"{transmission.reference} - {label}"
            transmission.display_name = label

    @api.model_create_multi
    def create(self, vals_list):
        transmissions = super().create(vals_list)
        transmissions._notify_subjects()
        transmissions.filtered(
            lambda transmission: transmission.state == "queued"
        ).channel_id._enqueue_send()
        return transmissions

    def write(self, vals):
        result = super().write(vals)
        if {"state", "intent"} & set(vals):
            self._notify_subjects()
        return result

    def unlink(self):
        self.env["exchange.transmission.dispatch"]._gc_unlinked(self.ids)
        return super().unlink()

    def _notify_subjects(self) -> None:
        for subject in {transmission.subject_id for transmission in self}:
            subject._on_transmission_changed()

    @api.model
    def _selection_document_kind(self) -> list[tuple[str, str]]:
        return self.env["exchange.protocol"]._selection_document_kind()

    @api.model
    def _selection_subject_models(self) -> list[tuple[str, str]]:
        mixin_cls = self.env.registry.get("mixin.exchange.subject")
        if not mixin_cls:
            return []

        subjects = []
        pending = list(mixin_cls._inherit_children)
        seen = set()
        while pending:
            name = pending.pop(0)
            if name in seen or name == "mixin.exchange.subject":
                continue
            seen.add(name)

            model_cls = self.env.registry.get(name)
            if not model_cls:
                continue
            pending.extend(model_cls._inherit_children)
            if not getattr(model_cls, "_abstract", False):
                subjects.append(
                    (name, getattr(model_cls, "_description", None) or name)
                )
        return sorted(subjects, key=lambda subject: subject[1])

    def _get_protocol(self):
        self.check_singleton()
        return self.channel_id._get_protocol()

    def action_send(self) -> None:
        self._send_many()

    def action_read_verdict(self) -> None:
        for transmission in self:
            transmission._read_verdict()

    def action_view_subject(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.subject_id._name,
            "res_id": self.subject_id.id,
            "view_mode": "form",
        }

    def _send(self) -> None:
        self.check_singleton()
        self._send_many()

    def _claim(self):
        claimed = self.try_lock_for_update(allow_referencing=True)
        if len(claimed) < len(self):
            _logger.info(
                "Left %s transmission(s) to the sender already holding them",
                len(self) - len(claimed),
            )
        return claimed

    def _send_many(self) -> None:
        ready = self.browse()
        claimed = self._claim()
        unanswered = self.env["exchange.transmission.dispatch"]._get_unanswered(
            claimed.ids
        )
        for transmission in claimed:
            if transmission.id in unanswered:
                _logger.info(
                    "Left transmission %s, whose last hand-off to the counterparty "
                    "has no recorded answer, to the sweep",
                    transmission.id,
                )
                continue
            if transmission.is_settled:
                raise UserError(
                    self.env._(
                        "Transmission %(name)s is settled and cannot be sent again.",
                        name=transmission.display_name,
                    ),
                )
            if transmission.state == "sent":
                _logger.info(
                    "Left transmission %s, which the counterparty already holds, "
                    "to its verdict",
                    transmission.id,
                )
                continue
            errors = transmission._get_protocol()._get_message_errors(transmission)
            if errors:
                transmission._settle(
                    Verdict(state="rejected", message="\n".join(errors)),
                )
            else:
                ready |= transmission

        grouped = ready.grouped(
            lambda transmission: (transmission.channel_id, transmission.document_kind)
        )
        for (channel, _kind), group in grouped.items():
            protocol = channel._get_protocol()
            size = max(getattr(protocol, "_batch_size", 1) or 1, 1)
            for start in range(0, len(group), size):
                group[start : start + size]._send_chunk(protocol)

    def _send_chunk(self, protocol) -> None:
        dispatched = self._claim_dispatch()
        if not dispatched:
            return
        try:
            outcomes = protocol._send_batch(dispatched)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception as error:
            _logger.exception(
                "Sending %s transmission(s) over %s failed",
                len(dispatched),
                dispatched.channel_id.display_name,
            )
            if isinstance(error, NotDelivered):
                dispatched._release_dispatch()
            now = fields.Datetime.now()
            for transmission in dispatched:
                if not isinstance(error, NotDelivered):
                    transmission.dispatch_count += 1
                transmission._record_failure(protocol, error, now)
            return

        undelivered = dispatched.filtered(
            lambda transmission: isinstance(outcomes.get(transmission.id), NotDelivered)
        )
        undelivered._release_dispatch()
        now = fields.Datetime.now()
        for transmission in dispatched:
            if transmission not in undelivered:
                transmission.dispatch_count += 1
            outcome = outcomes.get(transmission.id)
            if isinstance(outcome, Exception):
                _logger.error(
                    "Sending transmission %s over %s failed",
                    transmission.id,
                    transmission.channel_id.display_name,
                    exc_info=outcome,
                )
                transmission._record_failure(protocol, outcome, now)
                continue
            if outcome is None:
                _logger.warning(
                    "%s returned no verdict for transmission %s in a batch of %s",
                    protocol._name,
                    transmission.id,
                    len(dispatched),
                )
            transmission._record_answer(protocol, outcome, now)

    def _claim_dispatch(self):
        self.env.flush_all()
        with self._open_dispatch_cursor() as cr:
            claimed, lost = self.env(cr=cr)[
                "exchange.transmission.dispatch"
            ]._insert_claims(
                {
                    transmission.id: (
                        transmission.dispatch_count,
                        transmission._get_ask_identity(),
                        transmission.company_id.id,
                    )
                    for transmission in self
                }
            )
        held = self.filtered(
            lambda transmission: (
                transmission.id not in claimed and transmission.id not in lost
            )
        )
        if held:
            _logger.info(
                "Left %s transmission(s) another sender handed to the counterparty",
                len(held),
            )
        for transmission in self.browse(lost):
            _logger.info(
                "Left transmission %s unsent: a transmission of the same ask was "
                "handed to the counterparty in a transaction that did not commit",
                transmission.id,
            )
            transmission._update_lost_dispatch(*lost[transmission.id])
        return self.filtered(lambda transmission: transmission.id in claimed)

    def _release_dispatch(self) -> None:
        if not self:
            return
        with self._open_dispatch_cursor() as cr:
            self.env(cr=cr)["exchange.transmission.dispatch"]._release_claims(
                {transmission.id: transmission.dispatch_count for transmission in self}
            )

    @contextmanager
    def _open_dispatch_cursor(self) -> Iterator[BaseCursor]:
        with self.env.registry.cursor() as cr:
            cr.use_read_committed()
            cr.execute(
                SQL(
                    "SELECT set_config('lock_timeout', %s, true)",
                    DISPATCH_LOCK_TIMEOUT,
                )
            )
            yield cr

    def _get_ask_identity(self) -> str:
        self.check_singleton()
        subject = self.subject_id
        return "|".join(
            (
                f"{subject._name},{subject.id}",
                str(self.channel_id.id),
                self.intent,
                self.document_kind or "",
            )
        )

    def _record_answer(self, protocol, verdict: Verdict | None, date_sent) -> None:
        self.check_singleton()
        try:
            with self.env.cr.savepoint():
                self.date_sent = date_sent
                if verdict is None:
                    self._update_unknown_outcome(
                        protocol,
                        self.env._(
                            "The counterparty answered without naming this "
                            "document, so whether it was received is unknown."
                        ),
                    )
                else:
                    self._apply(verdict)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception as error:
            _logger.exception(
                "Recording the counterparty's answer to transmission %s failed",
                self.id,
            )
            self.date_sent = date_sent
            self._update_unknown_outcome(
                protocol,
                self.env._(
                    "The counterparty answered, but its answer could not be "
                    "recorded (%(error)s), so whether it was received is unknown.",
                    error=error,
                ),
            )

    def _record_failure(self, protocol, error: Exception, date_sent) -> None:
        self.check_singleton()
        if isinstance(error, NotDelivered):
            self._schedule_retry(str(error))
            return
        self.date_sent = date_sent
        self._update_unknown_outcome(
            protocol,
            self.env._(
                "The call carrying this document failed after it may have "
                "reached the counterparty (%(error)s), so whether it was "
                "received is unknown.",
                error=error,
            ),
        )

    def _update_unknown_outcome(self, protocol, cause: str) -> None:
        self.check_singleton()
        if protocol._is_reconcilable:
            self.write(
                {
                    "state": "sent",
                    "message": self.env._(
                        "%(cause)s It is not sent again: its outcome is read "
                        "back from the counterparty.",
                        cause=cause,
                    ),
                    "date_next_retry": False,
                    "date_reconcile_deadline": fields.Datetime.now()
                    + timedelta(days=self.channel_id.reconcile_window_days),
                },
            )
            return
        if protocol._is_resend_idempotent:
            attempt = self.retry_count + 1
            if self.channel_id.is_retry_required(attempt):
                self._schedule_retry(
                    self.env._(
                        "%(cause)s It is sent again, which the counterparty takes "
                        "only once.",
                        cause=cause,
                    ),
                )
            else:
                self._settle_unresolved(
                    self.env._(
                        "%(cause)s Gave up after %(attempts)s attempts. Check with "
                        "the counterparty whether it holds the document before "
                        "sending it again.",
                        cause=cause,
                        attempts=attempt,
                    ),
                )
            return
        self._settle_unresolved(
            self.env._(
                "%(cause)s It cannot be asked what became of the document, and "
                "sending the document again is not safe. Check with the "
                "counterparty whether it holds the document before sending it "
                "again.",
                cause=cause,
            ),
        )

    def _settle_unresolved(self, message: str) -> None:
        self.check_singleton()
        self._settle(Verdict(state="expired", message=message))
        self._react_subject("unresolved")

    def _read_verdict(self) -> None:
        self.check_singleton()
        if self.state != "sent":
            return
        verdict = self._get_protocol()._read_verdict(self)
        if verdict is not None:
            self._apply(verdict)
        else:
            self._settle_if_overdue(
                self.env._(
                    "The counterparty still has no record of this document, and "
                    "the time allowed to find it there has run out. Check with "
                    "the counterparty whether it holds the document before "
                    "sending it again."
                ),
            )

    def _settle_if_overdue(self, message: str) -> None:
        self.check_singleton()
        if (
            self.state == "sent"
            and self.date_reconcile_deadline
            and self.date_reconcile_deadline <= fields.Datetime.now()
        ):
            self._settle_unresolved(message)

    def _apply(self, verdict: Verdict) -> None:
        self.check_singleton()
        if verdict.is_settled:
            self._settle(verdict)
            return

        values = {
            "state": verdict.state,
            "date_next_retry": self._get_next_retry(verdict.retry_after),
            "date_reconcile_deadline": False,
            **verdict.values,
        }
        if verdict.reference:
            values["reference"] = verdict.reference
        if verdict.message:
            values["message"] = verdict.message
        self.write(values)
        self._add_response(verdict)

    def _settle(self, verdict: Verdict) -> None:
        self.check_singleton()
        values = {
            "state": verdict.state,
            "date_settled": fields.Datetime.now(),
            "date_next_retry": False,
            "date_reconcile_deadline": False,
            **verdict.values,
        }
        if verdict.reference:
            values["reference"] = verdict.reference
        if verdict.message:
            values["message"] = verdict.message
        self.write(values)
        self._add_response(verdict)
        self._react_subject("settled")

    def _react_subject(self, event: str) -> None:
        self.check_singleton()
        try:
            with self.env.cr.savepoint():
                self._get_subject_hook(event)(self)
        except Exception:
            _logger.exception(
                "The subject of transmission %s failed to react to it being %s; "
                "the reaction is retried as a job of its own",
                self.id,
                event,
            )
            self.delayed(
                identity_key=f"exchange.react:{self.id}:{event}",
                channel=f"exchange.{self.protocol}",
                name=f"React to transmission {self.id} being {event}",
            )._job_react_subject(event)

    @api.job(channel="exchange")
    def _job_react_subject(self, event: str) -> None:
        self.check_singleton()
        self._get_subject_hook(event)(self)

    def _get_subject_hook(self, event: str):
        return getattr(self.subject_id, _SUBJECT_HOOKS[event])

    def _schedule_retry(self, message: str) -> None:
        self.check_singleton()
        channel = self.channel_id
        attempt = self.retry_count + 1
        if not channel.is_retry_required(attempt):
            self._settle(
                Verdict(
                    state="rejected",
                    message=self.env._(
                        "Gave up after %(attempts)s attempts. Last error: %(message)s",
                        attempts=attempt,
                        message=message,
                    ),
                ),
            )
            return
        delay = channel.get_retry_delay(attempt)
        self.write(
            {
                "state": "queued",
                "retry_count": attempt,
                "message": message,
                "date_next_retry": fields.Datetime.now() + timedelta(seconds=delay),
            },
        )

    def _get_next_retry(self, retry_after: int | None):
        if retry_after is None:
            return False
        return fields.Datetime.now() + timedelta(seconds=retry_after)

    def _add_attachment(self, document) -> None:
        self.check_singleton()
        if self.attachment_id:
            return
        self.attachment_id = self.env["ir.attachment"].create(
            {
                "name": document.name or f"{self.id}.bin",
                "raw": document.data,
                "mimetype": document.mimetype,
                "res_model": self._name,
                "res_id": self.id,
            },
        )

    def _add_response(self, verdict: Verdict) -> None:
        self.check_singleton()
        if not verdict.response:
            return
        self.response_attachment_id = self.env["ir.attachment"].create(
            {
                "name": verdict.response_name or f"{self.id}-response.bin",
                "raw": verdict.response,
                "res_model": self._name,
                "res_id": self.id,
            },
        )

    @api.model
    def _get_due_domain(self, state: str = "queued") -> list:
        return [
            ("state", "=", state),
            "|",
            ("date_next_retry", "=", False),
            ("date_next_retry", "<=", fields.Datetime.now()),
        ]

    def _update_lost_dispatch(self, generation: int, date_dispatched) -> None:
        self.check_singleton()
        if self.state not in ("draft", "queued"):
            self.dispatch_count = generation
            return
        self.write({"dispatch_count": generation, "date_sent": date_dispatched})
        self._update_unknown_outcome(
            self._get_protocol(),
            self.env._(
                "The document was handed to the counterparty, but its answer was "
                "never recorded, so whether it was received is unknown."
            ),
        )

    @api.model
    def _update_lost_dispatches(self) -> None:
        dispatches = self.env["exchange.transmission.dispatch"]
        unanswered = dispatches._get_unanswered()
        for transmission in self.browse(unanswered).try_lock_for_update(
            allow_referencing=True
        ):
            generation, date_dispatched = unanswered[transmission.id]
            try:
                with self.env.cr.savepoint():
                    transmission._update_lost_dispatch(generation, date_dispatched)
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception:
                _logger.exception(
                    "Settling the lost hand-off of transmission %s failed",
                    transmission.id,
                )
        dispatches._gc_answered()

    @api.model
    def _cron_send_queued(self) -> None:
        self._update_lost_dispatches()
        self.env["exchange.channel"].union(
            *(
                channel
                for [channel] in self._read_group(
                    self._get_due_domain(), groupby=["channel_id"]
                )
            )
        )._enqueue_send()

    @api.model
    def _cron_read_verdicts(self, limit: int = 100) -> None:
        domain = self._get_due_domain("sent")
        polled_at = self.env.cr.now().replace(microsecond=0)
        if lastcall := fields.Datetime.to_datetime(self.env.context.get("lastcall")):
            domain += [
                "|",
                ("date_last_polled", "=", False),
                ("date_last_polled", "<=", lastcall),
            ]
            polled_at = max(polled_at, lastcall + timedelta(seconds=1))
        pending = self.search(
            domain, order="date_last_polled asc nulls first, id", limit=limit
        )
        pending.write({"date_last_polled": polled_at})
        for transmission in pending:
            try:
                with self.env.cr.savepoint():
                    transmission._read_verdict()
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception:
                _logger.exception(
                    "Reading the verdict of transmission %s failed", transmission.id
                )
                transmission._settle_if_overdue(
                    self.env._(
                        "The counterparty could not be asked what became of this "
                        "document before the time allowed to find it ran out. "
                        "Check with the counterparty whether it holds the document "
                        "before sending it again."
                    ),
                )
        self.env["ir.cron"]._commit_progress(
            len(pending),
            remaining=(
                self.search_count(domain) if lastcall and len(pending) == limit else 0
            ),
        )
