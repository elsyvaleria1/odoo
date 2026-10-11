import hashlib
import json
from datetime import UTC, datetime

from odoo import Command, api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import AccessError, UserError

INCIDENT_FIELDS = (
    "incident_type",
    "description",
    "odometer",
    "fuel_liters",
    "fuel_amount",
    "employee_id",
)
INCIDENT_LINE_FIELDS = ("picking_id", "product_id", "trace_id", "quantity")
APPLIERS = {
    "deliver": "_apply_deliver",
    "partial": "_apply_partial",
    "not_delivered": "_apply_not_delivered",
    "scan": "_apply_scan",
    "incident": "_apply_incident",
}
PHONE_INCIDENT_TYPES = ("spill", "damage", "theft", "breakdown", "other")
AFTER_DEPARTURE = ("deliver", "partial", "not_delivered", "scan")
BLOCKING_STATES = ("pending", "review")


class StockTripOfflineEvent(models.Model):

    _name = "stock.trip.offline.event"
    _description = "Trip Offline Event"
    _order = "captured_at, id"
    _rec_name = "client_uuid"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="batch_id.company_id",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery",
        index="btree_not_null",
    )
    event_type = fields.Selection(
        selection=[
            ("deliver", "Delivered"),
            ("partial", "Partial"),
            ("not_delivered", "Not delivered"),
            ("scan", "Code scanned"),
            ("incident", "Incident"),
        ],
        string="Event",
        required=True,
    )
    payload = fields.Json(
        help="What the phone captured, e.g. the lines of a partial delivery with "
        "the quantity taken and the reason, the reason and note of a stop not "
        "delivered, a scanned code or the incident reported.",
    )
    payload_display = fields.Text(
        string="Captured Data",
        compute="_compute_payload_display",
    )
    captured_at = fields.Datetime(
        string="Captured",
        required=True,
        help="When the driver recorded it, by the phone's clock.",
    )
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    device_uuid = fields.Char(
        string="Device",
        help="Phone that captured the event.",
    )
    client_uuid = fields.Char(
        string="Event UUID",
        readonly=True,
        required=True,
        help="Identifier the phone gives the event: sending it again does not "
        "record it twice.",
    )
    prev_hash = fields.Char(
        string="Previous Hash",
        readonly=True,
        help="The event_hash the phone chained this event to; empty for the "
        "trip's first event.",
    )
    event_hash = fields.Char(
        string="Hash",
        readonly=True,
        help="SHA-256 the phone computed over this event; see the README for the "
        "canonical form.",
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("applied", "Applied"),
            ("review", "To review"),
            ("dismissed", "Dismissed"),
        ],
        default="pending",
        readonly=True,
        required=True,
        help="Pending and To review events keep the trip from closing; a supervisor "
        "dismisses one after resolving it by hand.",
    )
    error = fields.Text(readonly=True)
    applied_at = fields.Datetime(
        string="Applied",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Sent By",
        default=lambda self: self.env.user,
        readonly=True,
        required=True,
    )

    _client_uuid_uniq = models.Constraint(
        "UNIQUE(client_uuid)",
        "An offline event is recorded only once.",
    )

    @api.depends("payload")
    def _compute_payload_display(self) -> None:
        for event in self:
            event.payload_display = json.dumps(event.payload or {}, indent=2)

    def _write_state(self, vals):
        return self.with_privilege(
            "stock_fleet_trace.privilege_trip_trace_record",
            reason="a trip applies its offline events",
        ).write(vals)

    def _capture_context(self) -> dict:
        self.check_singleton()
        return {
            "trip_offline_capture": {
                "date": fields.Datetime.to_string(self.captured_at),
                "latitude": self.latitude,
                "longitude": self.longitude,
                "client_uuid": self.client_uuid,
            },
            "trip_offline_applying": self.id,
        }

    def _apply(self):
        self.check_singleton()
        event = self.with_context(**self._capture_context())
        try:
            with self.env.cr.savepoint():
                getattr(event, APPLIERS[self.event_type])()
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception as error:
            message = (
                error.args[0]
                if isinstance(error, UserError) and error.args
                else f"{type(error).__name__}: {error}"
            )
            self._write_state({"state": "review", "error": message})
            self._notify_review()
        else:
            self._write_state(
                {
                    "state": "applied",
                    "applied_at": fields.Datetime.now(),
                    "error": False,
                }
            )

    def _notify_review(self) -> None:
        batch = self.batch_id
        batch.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=(batch.supervisor_id or self.env.user).id,
            summary=self.env._("Offline event of trip %s to review", batch.name),
            note=self.env._(
                "An event captured without connection on %(date)s could not be "
                "applied: %(error)s. Record it by hand and dismiss it.",
                date=self.captured_at,
                error=self.error,
            ),
        )

    def _stop(self):
        self.check_singleton()
        if not self.picking_id or self.picking_id.batch_id != self.batch_id:
            raise UserError(
                self.env._(
                    "%(picking)s is not a stop of trip %(batch)s.",
                    picking=self.picking_id.name or "-",
                    batch=self.batch_id.name,
                )
            )
        return self.picking_id

    def _apply_receiver(self, picking, payload):
        receiver_name = payload.get("receiver_name")
        signature = payload.get("signature")
        vals = {}
        if receiver_name:
            vals["trip_receiver_name"] = receiver_name
        if signature:
            vals["signature"] = signature
        if vals:
            picking.write(vals)
        return receiver_name

    def _apply_deliver(self) -> None:
        picking = self._stop()
        self._apply_receiver(picking, self.payload or {})
        picking.action_deliver()
        if picking.state != "done":
            raise UserError(
                self.env._(
                    "%s could not be validated from the phone: validate it by hand "
                    "to see what it asks.",
                    picking.name,
                )
            )
        picking.date_done = self.captured_at

    def _apply_partial(self) -> None:
        picking = self._stop()
        payload = self.payload or {}
        note = payload.get("note")
        if not note:
            raise UserError(
                self.env._(
                    "A partial delivery needs a note describing what the "
                    "customer took: the supervisor captures the quantities by "
                    "hand."
                )
            )
        receiver_name = self._apply_receiver(picking, payload)
        picking.trip_partial_review = True
        picking.message_post(
            body=self.env._(
                "Partial delivery captured offline. Received by: %(receiver)s. "
                "Note: %(note)s",
                receiver=receiver_name or self.env._("not given"),
                note=note,
            )
        )
        picking.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=(self.batch_id.supervisor_id or self.env.user).id,
            summary=self.env._("Capture the partial delivery of %s", picking.name),
            note=self.env._(
                "Captured offline without quantities: %(note)s. Use Partial to "
                "record what the customer took; confirming it clears the review.",
                note=note,
            ),
        )

    def _apply_not_delivered(self) -> None:
        payload = self.payload or {}
        self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {
                "picking_id": self._stop().id,
                "reason_id": payload.get("reason_id"),
                "note": payload.get("note"),
            }
        ).action_confirm()

    def _apply_scan(self) -> None:
        payload = self.payload or {}
        picking = self._stop() if self.picking_id else self.picking_id
        self.batch_id._trip_process_scan(
            payload.get("code"), payload.get("quantity") or None, picking
        )

    def _apply_incident(self) -> None:
        captured = (self.payload or {}).get("incident") or {}
        vals = {name: captured[name] for name in INCIDENT_FIELDS if name in captured}
        lines = [
            Command.create(
                {name: line[name] for name in INCIDENT_LINE_FIELDS if name in line}
            )
            for line in captured.get("lines", [])
        ]
        self.env["stock.trip.incident"].create(
            {
                **vals,
                "batch_id": self.batch_id.id,
                "date": self.captured_at,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "line_ids": lines,
            }
        )

    @staticmethod
    def _trip_hash_event(event):
        canonical = json.dumps(
            {
                "client_uuid": event.get("client_uuid"),
                "event_type": event.get("event_type"),
                "picking_id": event.get("picking_id"),
                "captured_at": event.get("captured_at"),
                "latitude": event.get("latitude"),
                "longitude": event.get("longitude"),
                "payload": event.get("payload") or {},
                "prev_hash": event.get("prev_hash") or "",
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @api.model
    def _trip_get_event_hash_error(self, event, chain_hash) -> tuple[str | bool, bool]:
        event_hash = event.get("event_hash")
        if not event_hash:
            return (
                self.env._("Offline event has no hash: it cannot be verified."),
                True,
            )
        if self._trip_hash_event(event) != event_hash:
            return (
                self.env._(
                    "Offline event %s was altered: its hash does not match its data.",
                    event.get("client_uuid"),
                ),
                True,
            )
        if (event.get("prev_hash") or "") != (chain_hash or ""):
            return (
                self.env._(
                    "Offline event %s breaks the chain: it does not follow the "
                    "previous event captured on this trip.",
                    event.get("client_uuid"),
                ),
                True,
            )
        return False, False

    def action_dismiss(self):
        for event in self:
            if event.state != "review":
                raise UserError(self.env._("Only an event to review can be dismissed."))
            if not (
                self.env.user == event.batch_id.supervisor_id
                or event.has_access("unlink")
            ):
                raise UserError(
                    self.env._(
                        "Offline events of trip %s are dismissed by its supervisor "
                        "or a stock manager.",
                        event.batch_id.name,
                    )
                )
            event._write_state({"state": "dismissed"})


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    trip_offline_event_ids = fields.One2many(
        comodel_name="stock.trip.offline.event",
        inverse_name="batch_id",
        string="Offline Events",
    )
    trip_offline_blocking_count = fields.Integer(
        string="Offline Events to Resolve",
        compute="_compute_trip_offline_blocking_count",
        help="Events sent from the phone that are pending or to review: the trip "
        "does not close nor unload until they are resolved.",
    )
    trip_offline_phone_head = fields.Char(
        string="Phone Head",
        copy=False,
        readonly=True,
        help="The phone's own latest event_hash, as it last reported it: while it "
        "differs from the last event received, the phone still holds unsent "
        "events.",
    )
    trip_offline_chain_broken = fields.Boolean(
        string="Offline Chain Broken",
        copy=False,
        help="An offline event's hash did not match its data, or did not follow "
        "the previous one: some events may have been altered or lost.",
    )

    @api.depends("trip_offline_event_ids.state")
    def _compute_trip_offline_blocking_count(self) -> None:
        for batch in self:
            batch.trip_offline_blocking_count = len(batch._trip_offline_blocking())

    def _trip_offline_blocking(self):
        applying = self.env.context.get("trip_offline_applying")
        return self.trip_offline_event_ids.filtered(
            lambda e: e.state in BLOCKING_STATES and e.id != applying
        )

    def _check_trip_offline_events_resolved(self) -> None:
        self.check_singleton()
        blocking = self._trip_offline_blocking()
        if blocking:
            raise UserError(
                self.env._(
                    "Trip %(batch)s has %(count)s offline events pending or to "
                    "review: resolve them first.",
                    batch=self.name,
                    count=len(blocking),
                )
            )

    def _check_trip_partial_review_resolved(self) -> None:
        self.check_singleton()
        pending = self.picking_ids.filtered("trip_partial_review")
        if pending:
            raise UserError(
                self.env._(
                    "Trip %(batch)s has %(count)s partial deliveries to capture "
                    "before its unloading is validated: %(pickings)s.",
                    batch=self.name,
                    count=len(pending),
                    pickings=", ".join(pending.mapped("name")),
                )
            )

    def _trip_last_event_hash(self):
        self.check_singleton()
        last = self.env["stock.trip.offline.event"].search(
            [("batch_id", "=", self.id), ("event_hash", "!=", False)],
            order="id desc",
            limit=1,
        )
        return last.event_hash or ""

    def _check_trip_offline_phone_head(self) -> None:
        self.check_singleton()
        head = self.trip_offline_phone_head
        if head and head != self._trip_last_event_hash():
            raise UserError(
                self.env._(
                    "Trip %s cannot return: the phone still holds unsent events.",
                    self.name,
                )
            )

    def _check_trip_offline_user(self) -> None:
        self.check_singleton()
        self.check_access("read")
        if self.env.user in self.operator_id.user_id | self.supervisor_id:
            return
        if self.env["stock.trip.offline.event"].has_access("unlink"):
            return
        raise AccessError(
            self.env._(
                "Trip %s is synced by its driver, its supervisor or a stock manager.",
                self.name,
            )
        )

    def _trip_offline_package(self, head=None) -> dict:
        self._check_trip_offline_user()
        if head:
            self.trip_offline_phone_head = head
        reasons = self.env["stock.picking.unbatch.reason"].search(
            [
                ("moment", "in", ("on_route", "any")),
                ("scope", "in", ("transfer", "both")),
            ]
        )
        incident_types = [
            (code, name)
            for code, name in self.env["stock.trip.incident"].fields_get(
                ["incident_type"], ["selection"]
            )["incident_type"]["selection"]
            if code in PHONE_INCIDENT_TYPES
        ]
        return {
            "trip": {
                "id": self.id,
                "name": self.name,
                "vehicle": self.vehicle_id.display_name or False,
                "operator": self.operator_id.name or False,
                "state": self.trip_state,
            },
            "stops": [
                picking._trip_offline_stop()
                for picking in self.picking_ids.sorted(
                    lambda p: (p.batch_sequence, p.id)
                )
            ],
            "unbatch_reasons": [
                {"id": reason.id, "name": reason.name, "scope": reason.scope}
                for reason in reasons
            ],
            "incident_types": [
                {"code": code, "name": name} for code, name in incident_types
            ],
            "server_time": fields.Datetime.to_string(fields.Datetime.now()),
        }

    def _trip_receive_offline_events(self, events, head=None) -> dict:
        self._check_trip_offline_user()
        Event = self.env["stock.trip.offline.event"]
        received = {
            event["client_uuid"]: event
            for event in events
            if isinstance(event, dict) and event.get("client_uuid")
        }
        known = set(
            Event.search([("client_uuid", "in", list(received))]).mapped("client_uuid")
        )
        chain_hash = self._trip_last_event_hash()
        chain_broken = False
        vals_list = []
        pickings = (
            self.env["stock.picking"]
            .browse(
                {e.get("picking_id") for e in received.values() if e.get("picking_id")}
                - {False, None}
            )
            .exists()
        )
        for uuid, event in received.items():
            if uuid in known:
                continue
            problems = []
            picking_id = event.get("picking_id") or False
            if picking_id and picking_id not in pickings.ids:
                problems.append(self.env._("Delivery %s does not exist.", picking_id))
                picking_id = False
            try:
                captured_at = _utc(event["captured_at"])
            except KeyError, TypeError, ValueError:
                problems.append(self.env._("The capture time cannot be read."))
                captured_at = fields.Datetime.now()
            if event.get("event_type") not in APPLIERS:
                problems.append(self.env._("Unknown event type."))
            vals = {
                "batch_id": self.id,
                "client_uuid": uuid,
                "event_type": event.get("event_type")
                if event.get("event_type") in APPLIERS
                else "incident",
                "picking_id": picking_id,
                "payload": event.get("payload") or {},
                "captured_at": captured_at,
                "latitude": event.get("latitude") or 0.0,
                "longitude": event.get("longitude") or 0.0,
                "device_uuid": event.get("device_uuid"),
                "prev_hash": event.get("prev_hash"),
                "event_hash": event.get("event_hash"),
            }
            error, broken = Event._trip_get_event_hash_error(event, chain_hash)
            if error:
                vals.update(state="review", error=error)
                chain_broken = chain_broken or broken
            if not error or Event._trip_hash_event(event) == event.get("event_hash"):
                chain_hash = event.get("event_hash")
            if problems and not error:
                vals.update(state="review", error="\n".join(problems))
            vals_list.append(vals)
        Event.create(vals_list)
        if chain_broken:
            if not self.trip_offline_chain_broken:
                self.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=(self.supervisor_id or self.env.user).id,
                    summary=self.env._(
                        "Offline events of trip %s do not verify", self.name
                    ),
                    note=self.env._(
                        "The hash chain sent from the phone for trip %s does not "
                        "check out: some events may have been altered or lost. "
                        "Review them before trusting the trip's record.",
                        self.name,
                    ),
                )
            self.trip_offline_chain_broken = True
        if head:
            self.trip_offline_phone_head = head
        self._trip_apply_offline_events()
        return {
            event.client_uuid: {"state": event.state, "error": event.error or False}
            for event in Event.search([("client_uuid", "in", list(received))])
        }

    def _trip_apply_offline_events(self) -> None:
        self.check_singleton()
        for event in self.trip_offline_event_ids.filtered(
            lambda e: (
                e.state == "pending"
                and (self.date_departure or e.event_type not in AFTER_DEPARTURE)
            )
        ).sorted("id"):
            event._apply()


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _trip_offline_stop(self) -> dict:
        self.check_singleton()
        partner = self.partner_id
        latitude, longitude = self._trip_location() or (0.0, 0.0)
        return {
            "picking_id": self.id,
            "name": self.name,
            "state": self.state,
            "partner": partner.display_name or False,
            "address": partner.contact_address or False,
            "latitude": latitude,
            "longitude": longitude,
            "lines": [
                {
                    "move_line_id": line.id,
                    "product_id": line.product_id.id,
                    "product": line.product_id.display_name,
                    "trace_id": line.trace_id.id,
                    "lot": line.trace_id.name or False,
                    "quantity": line.quantity,
                    "uom": line.product_uom_id.name,
                }
                for line in self.move_ids.move_line_ids
                if line.state not in ("done", "cancel")
            ],
        }


def _utc(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo:
        moment = moment.astimezone(UTC).replace(tzinfo=None)
    return moment
