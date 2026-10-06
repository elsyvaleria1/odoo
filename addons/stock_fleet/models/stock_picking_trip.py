from odoo import fields, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

# The two ways a pending transfer leaves a trip that has departed: as not
# delivered, when the goods travelled and came back, or as a correction, when the
# transfer never should have travelled on that trip.
UNBATCH_UNDELIVERED = "trip_unbatch_undelivered"
UNBATCH_CORRECTION = "trip_unbatch_correction"
# Merging trips moves their transfers into one on purpose.
MERGE_TRIPS = "trip_merge"


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    dispatch_batch_required = fields.Boolean(
        string="Deliver in Trips",
        tracking=True,
        help="Outgoing transfers of this type are validated only inside a trip that "
        "has departed with its vehicle, operator and supervisor.",
    )


class StockPicking(models.Model):
    _inherit = "stock.picking"

    delivery_failure_reason = fields.Text(
        copy=False,
        tracking=True,
        help="Why the goods came back undelivered on the last trip.",
    )
    delivery_failure_reason_id = fields.Many2one(
        comodel_name="stock.picking.unbatch.reason",
        string="Undelivered Reason",
        index="btree_not_null",
        copy=False,
        tracking=True,
        help="The catalogue reason the transfer came back undelivered on its last "
        "trip.",
    )
    trip_date_departure = fields.Datetime(
        related="batch_id.date_departure",
        string="Trip Departure",
        help="When the trip carrying this transfer left; empty until it does.",
    )

    def _requires_trip(self):
        """Whether this transfer may only be validated inside a departed trip:
        its type asks for trips and its goods ride the trip's vehicle.

        :rtype: bool
        """
        self.check_singleton()
        return bool(
            self.picking_type_id.dispatch_batch_required and self._rides_trip_vehicle()
        )

    def _rides_trip_vehicle(self) -> bool:
        """Whether the goods of this transfer travel on the vehicle of its trip.

        Whatever the operation type asks for: who reads the vehicle (its GPS)
        needs to know what it carries even where trips are not compulsory.
        Bridges narrow it, e.g. by the carrier that takes the goods.

        :rtype: bool
        """
        self.check_singleton()
        return bool(
            self.picking_type_id.code == "outgoing"
            and not ("pos_session_id" in self._fields and self.pos_session_id)
        )

    def _trip_vehicle_returns(self) -> bool:
        """Whether the vehicle goes back to the trip's warehouse after this transfer.

        :rtype: bool
        """
        self.check_singleton()
        return True

    def _check_dispatch_requirements(self) -> None:
        """Refuse to validate a transfer that must travel in a trip outside one.

        Reads the transfer's own batch: a batch validates its transfers twice, the
        first time without passing itself along.
        """
        for picking in self:
            if not picking._requires_trip():
                continue
            batch = picking.batch_id
            if not batch:
                raise UserError(
                    self.env._(
                        "Transfer %(name)s leaves on a vehicle and must be delivered "
                        "from a trip. Add it to a trip and register the departure first.",
                        name=picking.name,
                    )
                )
            if not batch.date_departure:
                raise UserError(
                    self.env._(
                        "Transfer %(name)s belongs to trip %(batch)s, which has not "
                        "departed. Register the departure first.",
                        name=picking.name,
                        batch=batch.name,
                    )
                )

    def _get_domain_possible_batches(self, excluded_batches=None):
        # Auto-batching must not board a transfer onto a trip that already left.
        return super()._get_domain_possible_batches(excluded_batches) & Domain(
            "date_departure", "=", False
        )

    def _check_before_validation(self, batch=None):
        self._check_dispatch_requirements()
        return super()._check_before_validation(batch=batch)

    def write(self, vals):
        if "batch_id" in vals:
            self._check_departed_trip_keeps_its_pickings(vals["batch_id"])
            self._check_transfer_rides_one_trip(vals["batch_id"])
        if vals.get("batch_id"):
            trip = self.env["stock.picking.batch"].browse(vals["batch_id"])
            if trip.date_departure:
                trip._check_trip_takes_no_new_pickings(
                    self.filtered(lambda picking: picking.batch_id != trip)
                )
        # A departed trip is the record of what the vehicle carried: a delivered
        # transfer stays on it when the batch sheds its done transfers.
        if "batch_id" in vals and not vals["batch_id"]:
            kept = self.filtered(
                lambda picking: (
                    picking.state == "done" and picking.batch_id.date_departure
                )
            )
            if kept:
                rest = self - kept
                kept_vals = {
                    key: value for key, value in vals.items() if key != "batch_id"
                }
                if kept_vals:
                    super(StockPicking, kept).write(kept_vals)
                return super(StockPicking, rest).write(vals) if rest else True
        return super().write(vals)

    def _check_departed_trip_keeps_its_pickings(self, batch) -> None:
        """Refuse to take a pending transfer off a trip that has departed.

        :param batch: the batch the transfers move to, as an id, a record or False
        """
        if self.env.context.get(UNBATCH_UNDELIVERED):
            return
        # The context alone does not open the way: the caller must hold the access
        # of the correction wizard, which belongs to the trip corrections group.
        if self.env.context.get(UNBATCH_CORRECTION) and self.env[
            "wizard.stock.picking.unbatch.correction"
        ].has_access("create"):
            return
        batch_id = batch.id if isinstance(batch, models.BaseModel) else batch or False
        leaving = self.filtered(
            lambda picking: (
                picking.batch_id.date_departure
                and picking.batch_id.id != batch_id
                and picking.state not in ("done", "cancel")
            )
        )
        if leaving:
            _debug.logic(
                "trip_keeps_pending_pickings",
                pickings=leaving,
                batches=leaving.batch_id,
            )
            # The refusal carries the way out: the reasons, for the first transfer.
            raise RedirectWarning(
                self.env._(
                    "%(pickings)s travels on trip %(batch)s, which has already "
                    "departed. A transfer comes off it only as not delivered, with "
                    "its reason.",
                    pickings=", ".join(leaving.mapped("name")),
                    batch=", ".join(leaving.batch_id.mapped("name")),
                ),
                leaving[:1].action_not_delivered(),
                self.env._("Register as not delivered"),
            )

    def _check_transfer_rides_one_trip(self, batch) -> None:
        """Refuse to put a transfer that is on a trip into another batch.

        Before departure the transfer leaves its trip freely; it is moved only once
        it has been taken off, so that no trip loses a stop without anyone noticing.

        :param batch: the batch the transfers move to, as an id, a record or False
        """
        if self.env.context.get(MERGE_TRIPS):
            return
        batch_id = batch.id if isinstance(batch, models.BaseModel) else batch or False
        if not batch_id:
            return
        # Only where transfers are delivered in trips: elsewhere batches and waves
        # regroup transfers freely, as stock_picking_batch intends.
        on_other_trip = self.filtered(
            lambda picking: (
                picking.batch_id
                and picking.batch_id.id != batch_id
                and picking.picking_type_id.dispatch_batch_required
            )
        )
        if on_other_trip:
            _debug.logic(
                "trip_keeps_its_transfer",
                pickings=on_other_trip,
                batches=on_other_trip.batch_id,
            )
            raise UserError(
                self.env._(
                    "%(pickings)s is already on %(batch)s. Take it off that batch "
                    "before adding it to another one.",
                    pickings=", ".join(on_other_trip.mapped("name")),
                    batch=", ".join(on_other_trip.batch_id.mapped("name")),
                )
            )

    def _detach_from_batch_before_backorder(self):
        # A transfer partly delivered on a departed trip stays on it, since the trip
        # records what it delivered; its backorder is born off the trip.
        on_trip = self.filtered(lambda picking: picking.batch_id.date_departure)
        if on_trip:
            _debug.logic("trip_keeps_partial_delivery", pickings=on_trip)
        return super(StockPicking, self - on_trip)._detach_from_batch_before_backorder()

    # ------------------------------------------------------------------
    # The driver's outcome per stop
    # ------------------------------------------------------------------
    def action_deliver(self):
        """Driver button: the customer received the goods as loaded."""
        self.check_singleton()
        if self.state != "assigned":
            raise UserError(
                self.env._(
                    "Transfer %(name)s is not ready to deliver (%(state)s).",
                    name=self.name,
                    state=dict(self._fields["state"].selection).get(self.state),
                )
            )
        if not self.batch_id.date_departure:
            raise UserError(
                self.env._("Transfer %s is not on a trip that has departed.", self.name)
            )
        self.move_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
        ).picked = True
        result = self.button_validate(skip_backorder=True)
        self.batch_id._close_trip_at_last_stop()
        return result

    def action_not_delivered(self) -> dict:
        """Driver button: the goods come back; ask why."""
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Not delivered"),
            "res_model": "wizard.stock.picking.unbatch.undelivered",
            "view_mode": "form",
            # A RedirectWarning hands the action to the client as is, with no
            # server pass to derive its views from view_mode.
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_picking_id": self.id},
        }

    def _register_delivery_failure(self, reason):
        """Take the transfer off its trip with the reason on both records.

        The transfer stays ready, in transit, for the next trip.

        :param str reason: why the goods were not delivered
        """
        self.check_singleton()
        batch = self.batch_id
        _debug.lifecycle("trip_delivery_failure", pickings=self, batches=batch)
        self.with_context(**{UNBATCH_UNDELIVERED: True}).write(
            {"delivery_failure_reason": reason, "batch_id": False}
        )
        self.message_post(
            body=self.env._(
                "Not delivered on trip %(batch)s: %(reason)s",
                batch=batch.name or "-",
                reason=reason,
            )
        )
        if batch:
            batch.message_post(
                body=self.env._(
                    "%(picking)s came back undelivered: %(reason)s",
                    picking=self.name,
                    reason=reason,
                )
            )
            if batch.picking_ids:
                batch._close_trip_at_last_stop()

    def _take_off_trip_as_correction(self, reason):
        """Take pending transfers off their departed trip as they are.

        Nothing failed on the route: no undelivered reason is set and the transfers
        keep their state and reservation, ready for another trip.

        :param str reason: why the transfers should not have travelled on the trip
        """
        trip = self.batch_id
        trip.check_singleton()
        trip_state = dict(
            trip._fields["trip_state"]._description_selection(self.env)
        ).get(trip.trip_state)
        _debug.lifecycle("trip_unbatch_correction", pickings=self, batches=trip)
        self.with_context(**{UNBATCH_CORRECTION: True}).write({"batch_id": False})
        for picking in self:
            picking.message_post(
                body=self.env._(
                    "Taken off trip %(batch)s (%(state)s) as a correction: %(reason)s",
                    batch=trip.name,
                    state=trip_state,
                    reason=reason,
                )
            )
        trip.message_post(
            body=self.env._(
                "%(pickings)s taken off the trip as a correction: %(reason)s",
                pickings=", ".join(self.mapped("name")),
                reason=reason,
            )
        )
