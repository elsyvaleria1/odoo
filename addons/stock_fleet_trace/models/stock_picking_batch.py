from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from odoo.tools.authority_keys import declare_authority_keys

from odoo.addons.stock_fleet.models.stock_picking_trip import (
    MERGE_TRIPS,
    UNBATCH_UNDELIVERED,
)

# lets a delivery leave a loaded trip, or join one: never a caller's to pass
declare_authority_keys("stock_fleet_trace", "trip_handover")


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    trip_state = fields.Selection(
        selection_add=[
            ("planned",),
            ("loaded", "Loaded"),
            ("in_transit",),
            ("returned", "Returned"),
        ],
        ondelete={"loaded": "set null", "returned": "set null"},
    )
    has_trip_trace = fields.Boolean(related="picking_type_id.trip_trace")
    date_loaded = fields.Datetime(
        string="Loaded",
        copy=False,
        readonly=True,
        help="When the goods of the trip moved onto the vehicle.",
    )
    trip_location_ids = fields.Many2many(
        comodel_name="stock.location",
        relation="stock_picking_batch_trip_location_rel",
        string="Vehicle Locations",
        copy=False,
        readonly=True,
        help="The vehicle's locations that held this trip's goods.",
    )
    fuel_unit = fields.Selection(
        selection=[("percent", "% of tank"), ("liter", "Litres")],
        default="percent",
        required=True,
    )
    fuel_departure = fields.Float(
        string="Fuel at Departure",
        copy=False,
        tracking=True,
    )
    fuel_return = fields.Float(
        string="Fuel at Return",
        copy=False,
        tracking=True,
    )
    weight_departure = fields.Float(
        string="Weight at Departure",
        digits="Stock Weight",
        copy=False,
        readonly=True,
        help="Theoretical weight of the goods loaded, frozen when the trip loaded: "
        "the product weights times the quantities, without pallets or packaging.",
    )
    weight_on_board = fields.Float(
        digits="Stock Weight",
        compute="_compute_weight_on_board",
        help="Theoretical weight of the goods on the vehicle now.",
    )
    trip_checkpoint_ids = fields.One2many(
        comodel_name="stock.trip.checkpoint",
        inverse_name="batch_id",
        string="Checkpoints",
    )
    trip_incident_ids = fields.One2many(
        comodel_name="stock.trip.incident",
        inverse_name="batch_id",
        string="Incidents",
    )
    trip_incident_open_count = fields.Integer(
        string="Incidents to Review",
        compute="_compute_trip_incident_open_count",
    )
    trip_balance_ids = fields.One2many(
        comodel_name="stock.trip.balance",
        inverse_name="batch_id",
        string="Balance",
    )
    trip_support_picking_ids = fields.One2many(
        comodel_name="stock.picking",
        inverse_name="trip_support_batch_id",
        string="Loading and Unloading",
    )
    unload_picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Unloading",
        copy=False,
        readonly=True,
    )
    balance_state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("balanced", "Balanced"),
            ("difference", "With difference"),
        ],
        copy=False,
        readonly=True,
        tracking=True,
        help="Whether what came back matches what the trip loaded, less what it "
        "delivered, wrote off and handed over.",
    )
    handover_from_batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Taken Over From",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Trip whose load this one took over after a breakdown.",
    )

    @api.depends(
        "state",
        "date_departure",
        "date_return",
        "picking_type_id.dispatch_management",
        "date_loaded",
        "unload_picking_id.state",
    )
    def _compute_trip_state(self) -> None:
        super()._compute_trip_state()
        for batch in self:
            if batch.trip_state == "planned" and batch.date_loaded:
                batch.trip_state = "loaded"
            elif batch.trip_state == "closed" and batch.unload_picking_id.state not in (
                False,
                "done",
                "cancel",
            ):
                batch.trip_state = "returned"

    def _trip_closes_at_last_stop(self) -> bool:
        # goods refused on a traced trip ride back to be unloaded and counted
        return super()._trip_closes_at_last_stop() and not self.has_trip_trace

    @api.depends("trip_location_ids")
    def _compute_weight_on_board(self) -> None:
        for batch in self:
            batch.weight_on_board = batch._trip_weight_on_board()

    @api.depends("trip_incident_ids.state")
    def _compute_trip_incident_open_count(self) -> None:
        for batch in self:
            batch.trip_incident_open_count = len(
                batch.trip_incident_ids.filtered(lambda i: i.state == "reported")
            )

    def write(self, vals):
        if "picking_ids" in vals:
            loaded = {
                batch: batch.picking_ids
                for batch in self.filtered(
                    lambda b: b.date_loaded and not b.date_departure
                )
            }
            res = super().write(vals)
            for batch, before in loaded.items():
                batch._check_trip_loaded_takes_no_new_pickings(
                    batch.picking_ids - before
                )
                batch._check_trip_loaded_keeps_its_pickings(before - batch.picking_ids)
            return res
        return super().write(vals)

    def _check_trip_loaded_takes_no_new_pickings(self, added) -> None:
        if added:
            raise UserError(
                self.env._(
                    "Trip %(batch)s is already loaded; %(pickings)s cannot be added. "
                    "Unload it first or put them on the next trip.",
                    batch=self.name,
                    pickings=", ".join(added.mapped("name")),
                )
            )

    def _check_trip_vehicle_empty(self):
        """A vehicle loads a trip only once the goods of its last trip are off."""
        self.check_singleton()
        leftover = self.env["stock.quant"].search(
            [
                ("location_id.trip_vehicle_id", "=", self.vehicle_id.id),
                ("quantity", ">", 0),
            ],
            limit=1,
        )
        if leftover:
            raise UserError(
                self.env._(
                    "%(vehicle)s still carries goods of an earlier trip in "
                    "%(location)s: confirm that trip's unloading before loading "
                    "trip %(batch)s.",
                    vehicle=self.vehicle_id.display_name,
                    location=leftover.location_id.display_name,
                    batch=self.name,
                )
            )

    def _check_trip_loaded_keeps_its_pickings(self, removed):
        """A delivery whose goods are on the vehicle leaves only once unloaded."""
        self.check_singleton()
        on_board = removed.move_ids.move_line_ids.filtered(
            lambda line: (
                line.state not in ("done", "cancel")
                and line.location_id in self.trip_location_ids
            )
        )
        if on_board and not self.env.context.get("trip_handover"):
            raise UserError(
                self.env._(
                    "Trip %(batch)s is loaded: %(pickings)s cannot leave it while "
                    "its goods are on the vehicle. Unload the trip first.",
                    batch=self.name,
                    pickings=", ".join(on_board.picking_id.mapped("name")),
                )
            )

    def action_cancel(self):
        # Read from the vehicle now, not from a weight computed before the unload.
        loaded = self.filtered(
            lambda b: (
                b.date_loaded
                and not b.date_departure
                and b._trip_quants().filtered(lambda q: q.quantity > 0)
            )
        )
        if loaded:
            raise UserError(
                self.env._(
                    "Trip %s still has its goods on the vehicle: unload it before "
                    "cancelling.",
                    ", ".join(loaded.mapped("name")),
                )
            )
        return super().action_cancel()

    # ------------------------------------------------------------------
    # Checkpoints
    # ------------------------------------------------------------------
    def _trip_checkpoint(self, event_type, **vals):
        """Record an event on the trip's log.

        :param str event_type: a checkpoint type
        :return: the checkpoint
        :rtype: recordset
        """
        self.check_singleton()
        method = self.env.context.get("trip_checkpoint_method")
        if method:
            vals.setdefault("method", method)
        # An event captured on the phone keeps its own time and place, and is
        # someone's word however it was captured.
        offline = self.env.context.get("trip_offline_capture")
        if offline:
            note = self.env._("Captured offline %s", offline["client_uuid"])
            vals.update(
                date=offline["date"],
                latitude=vals.get("latitude") or offline["latitude"],
                longitude=vals.get("longitude") or offline["longitude"],
                method="manual",
                note=f"{vals['note']}\n{note}" if vals.get("note") else note,
            )
        return (
            self.env["stock.trip.checkpoint"]
            .with_privilege(
                "stock_fleet_trace.privilege_trip_trace_record",
                reason="a trip records its own log",
            )
            .create(
                {
                    "batch_id": self.id,
                    "event_type": event_type,
                    "user_id": self.env.uid,
                    "weight_on_board": self._trip_weight_on_board(),
                    **vals,
                }
            )
        )

    def action_trip_verify_log(self) -> dict:
        """Check that no checkpoint was altered since it was sealed."""
        self.check_singleton()
        broken = self.trip_checkpoint_ids._check_chain()
        if broken:
            raise UserError(
                self.env._(
                    "The log of trip %(batch)s was altered at checkpoint(s) %(seq)s.",
                    batch=self.name,
                    seq=", ".join(str(s) for s in broken.mapped("sequence")),
                )
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._(
                    "The %(count)s checkpoints of trip %(batch)s are intact.",
                    count=len(self.trip_checkpoint_ids),
                    batch=self.name,
                ),
            },
        }

    # ------------------------------------------------------------------
    # What is on the vehicle
    # ------------------------------------------------------------------
    def _trip_quants(self):
        self.check_singleton()
        return self._trip_quants_in(self.trip_location_ids)

    @api.model
    def _trip_quants_in(self, locations):
        """The goods in ``locations``, as stock quants with a quantity.

        :rtype: recordset
        """
        if not locations:
            return self.env["stock.quant"]
        return self.env["stock.quant"].search(
            [("location_id", "in", locations.ids), ("quantity", ">", 0)]
        )

    def _trip_weight_on_board(self):
        self.check_singleton()
        if self.date_return and self.unload_picking_id.state == "done":
            return 0.0
        return self._trip_weight_on_board_of(self.trip_location_ids)

    def _trip_location_holding(self, product, lot):
        """Return the vehicle location of this trip holding ``product``/``lot``."""
        self.check_singleton()
        quants = self._trip_quants().filtered(
            lambda q: q.product_id == product and (not lot or q.trace_id == lot)
        )
        return quants[:1].location_id

    def _trip_free_reservation(
        self, location, product, lot, quantity, picking=None
    ) -> None:
        """Release ``quantity`` of the deliveries' reservation in ``location``.

        Goods lost on the route can no longer be delivered; the deliveries that
        counted on them stop holding them, the named one first.
        """
        self.check_singleton()
        lines = self.env["stock.move.line"].search(
            [
                ("location_id", "=", location.id),
                ("product_id", "=", product.id),
                ("state", "not in", ("done", "cancel")),
            ]
        )
        if lot:
            lines = lines.filtered(lambda ml: ml.trace_id == lot)
        if picking:
            lines = lines.sorted(lambda ml: ml.picking_id != picking)
        # Goods nobody reserved (a rejection) are lost first: no customer's
        # delivery shrinks while free goods of the same product are on board.
        quants = self.env["stock.quant"].search(
            [("location_id", "=", location.id), ("product_id", "=", product.id)]
            + ([("trace_id", "=", lot.id)] if lot else [])
        )
        free = sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity"))
        remaining = quantity - max(free, 0.0)
        for line in lines:
            if remaining <= 0:
                break
            taken = min(line.quantity_product_uom, remaining)
            line.quantity = line.product_id.uom_id._get_quantity_in_unit(
                line.quantity_product_uom - taken, line.product_uom_id
            )
            self._trip_record_written_off(
                line.picking_id, line.product_id._trip_weight(taken)
            )
            remaining -= taken

    # ------------------------------------------------------------------
    # Moving goods onto, between and off vehicles
    # ------------------------------------------------------------------
    def _trip_support_picking(self, source, destination, kind):
        self.check_singleton()
        warehouse = self.picking_type_id.warehouse_id
        return self.env["stock.picking"].create(
            {
                "picking_type_id": warehouse.int_type_id.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "origin": self.name,
                "trip_support_batch_id": self.id,
                "trip_support_kind": kind,
                "company_id": self.company_id.id,
            }
        )

    def _trip_reroute(self, moves, destination, kind, picking, target=None):
        """Put a leg in front of pending deliveries, carrying what they reserved.

        Each delivery keeps its goods: its reservation is released, a move takes
        the same lots from where they are to ``destination``, and that move becomes
        the one the delivery draws from, so the chain SHIP -> leg -> OUT holds.

        :param recordset moves: pending outgoing moves with reserved lines
        :param recordset destination: where the leg leaves the goods
        :param str kind: the trip movement kind of the leg
        :param recordset picking: the internal transfer the legs belong to
        :param recordset target: on a handover, the trip receiving the goods
        :return: the legs created
        :rtype: recordset
        """
        self.check_singleton()
        Move = self.env["stock.move"]
        legs = Move
        plans = []
        for move in moves:
            reserved = [
                (
                    ml.location_id,
                    ml.trace_id,
                    ml.package_id,
                    ml.owner_id,
                    ml.quantity_product_uom,
                )
                for ml in move.move_line_ids
                if ml.quantity and ml.state not in ("done", "cancel")
            ]
            if not reserved:
                continue
            move._unreserve()
            leg = Move.create(
                {
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_id.uom_id.id,
                    "product_uom_qty": sum(line[4] for line in reserved),
                    "location_id": picking.location_id.id,
                    "location_dest_id": destination.id,
                    "picking_id": picking.id,
                    "company_id": move.company_id.id,
                    "origin": move.picking_id.name,
                    "move_orig_ids": [Command.set(move.move_orig_ids.ids)],
                    "move_dest_ids": [Command.set(move.ids)],
                    "trip_batch_id": self.id,
                    "trip_move_kind": kind,
                    "trip_target_batch_id": target.id if target else False,
                }
            )
            move.move_orig_ids = [Command.set(leg.ids)]
            plans.append((leg, reserved))
            legs |= leg
        if not legs:
            return legs
        legs._action_confirm(merge=False)
        # Confirming may reserve on its own; the legs carry exactly what was held.
        legs._unreserve()
        for leg, reserved in plans:
            self.env["stock.move.line"].create(
                [
                    {
                        "move_id": leg.id,
                        "picking_id": picking.id,
                        "product_id": leg.product_id.id,
                        "product_uom_id": leg.product_id.uom_id.id,
                        "location_id": location.id,
                        "location_dest_id": destination.id,
                        "trace_id": lot.id,
                        "package_id": package.id,
                        "owner_id": owner.id,
                        "quantity": quantity,
                    }
                    for location, lot, package, owner, quantity in reserved
                ]
            )
        return legs

    def _trip_move_free_goods(self, location, destination, kind, picking, target=None):
        """Move what nobody reserved in ``location`` (rejections, surplus)."""
        self.check_singleton()
        Move = self.env["stock.move"]
        free = defaultdict(list)
        quants = self.env["stock.quant"].search(
            [("location_id", "=", location.id), ("quantity", ">", 0)]
        )
        for quant in quants:
            available = quant.quantity - quant.reserved_quantity
            if not float_is_zero(
                available, precision_rounding=quant.product_uom_id.rounding
            ):
                free[quant.product_id].append(
                    (quant.trace_id, quant.package_id, available)
                )
        moves = Move
        for product, lines in free.items():
            move = Move.create(
                {
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "product_uom_qty": sum(line[2] for line in lines),
                    "location_id": location.id,
                    "location_dest_id": destination.id,
                    "picking_id": picking.id,
                    "company_id": picking.company_id.id,
                    "origin": self.name,
                    "trip_batch_id": self.id,
                    "trip_move_kind": kind,
                    "trip_target_batch_id": target.id if target else False,
                }
            )
            move._action_confirm(merge=False)
            move._unreserve()
            self.env["stock.move.line"].create(
                [
                    {
                        "move_id": move.id,
                        "picking_id": picking.id,
                        "product_id": product.id,
                        "product_uom_id": product.uom_id.id,
                        "location_id": location.id,
                        "location_dest_id": destination.id,
                        "trace_id": lot.id,
                        "package_id": package.id,
                        "quantity": quantity,
                    }
                    for lot, package, quantity in lines
                ]
            )
            moves |= move
        return moves

    @staticmethod
    def _trip_validate_support(picking) -> None:
        picking.move_ids.picked = True
        # Whether an expired lot may travel was decided on the deliveries (the
        # expired-lot guard); moving it between our own locations asks nothing.
        picking.with_context(skip_expired=True).button_validate(skip_backorder=True)
        if picking.state != "done":
            # A wizard left unanswered would leave the goods off the vehicle while
            # the trip reads loaded.
            raise UserError(
                picking.env._(
                    "Transfer %s of the trip could not be validated: validate it "
                    "by hand to see what it asks, then try again.",
                    picking.name,
                )
            )

    def _trip_pending_delivery_moves(self, locations):
        """Outgoing moves still holding goods in ``locations``."""
        return (
            self.env["stock.move.line"]
            .search(
                [
                    ("location_id", "in", locations.ids),
                    ("state", "not in", ("done", "cancel")),
                    ("move_id.picking_code", "=", "outgoing"),
                ]
            )
            .move_id
        )

    # ------------------------------------------------------------------
    # Loading, departure, return, unloading
    # ------------------------------------------------------------------
    def _trip_departure_missing(self):
        missing = super()._trip_departure_missing()
        if self.has_trip_trace and not self.fuel_departure:
            missing.append(self.env._("Fuel at departure"))
        return missing

    def action_trip_load(self) -> None:
        """Move the goods of every delivery onto the vehicle."""
        self.check_singleton()
        if self.date_loaded:
            raise UserError(self.env._("Trip %s is already loaded.", self.name))
        if not self.has_trip_trace:
            raise UserError(
                self.env._(
                    "Trip %s is not of an operation type that traces its load on the "
                    "vehicle.",
                    self.name,
                )
            )
        if not self.vehicle_id:
            raise UserError(self.env._("Trip %s has no vehicle.", self.name))
        if not self.picking_ids:
            raise UserError(self.env._("Trip %s has no deliveries.", self.name))
        not_ready = self.picking_ids.filtered(lambda p: p.state != "assigned")
        if not_ready:
            raise UserError(
                self.env._(
                    "Trip %(batch)s cannot load deliveries that are not ready: "
                    "%(pickings)s.",
                    batch=self.name,
                    pickings=", ".join(not_ready.mapped("name")),
                )
            )
        # Without it no delivery requires a trip, and every one would be
        # blamed below on a carrier it does not have.
        if not self.picking_type_id.dispatch_batch_required:
            raise UserError(
                self.env._(
                    "Trip %(batch)s cannot load: operation type %(type)s does not "
                    'require its deliveries to leave in a trip. Enable "Deliver in '
                    'Trips" on it first.',
                    batch=self.name,
                    type=self.picking_type_id.display_name,
                )
            )
        # Goods that leave with a third-party carrier or the customer never
        # board our vehicle; stock_fleet_delivery tells them apart.
        off_fleet = self.picking_ids.filtered(lambda p: not p._requires_trip())
        if off_fleet:
            raise UserError(
                self.env._(
                    "Trip %(batch)s cannot load %(pickings)s: they leave with a "
                    "third-party carrier or the customer, not on our vehicle. Take "
                    "them out of the trip.",
                    batch=self.name,
                    pickings=", ".join(off_fleet.mapped("name")),
                )
            )
        # Expired product does not leave the warehouse without an approver's
        # signature: where the delivery still draws from inside it (one-step
        # warehouses), the check happens here, before the goods board.
        for picking in self.picking_ids:
            if hasattr(picking, "_check_no_expired_lots"):
                picking._check_no_expired_lots()
        self._check_trip_vehicle_empty()
        # "Deliver all at once" is met here: every delivery is fully reserved.
        # From now on what travels is what is on board, and a loss or a handover
        # must not hold the rest of the delivery back.
        self.picking_ids.filtered(lambda p: p.move_type == "one").write(
            {"move_type": "direct"}
        )
        moves = self.picking_ids.move_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
        )
        moves.write({"trip_batch_id": self.id, "trip_move_kind": "delivery"})
        locations = self.env["stock.location"]
        for source, group in moves.grouped("location_id").items():
            vehicle_location = source._get_or_create_trip_vehicle_location(
                self.vehicle_id
            )
            picking = self._trip_support_picking(source, vehicle_location, "load")
            self._trip_reroute(group, vehicle_location, "load", picking)
            self._trip_validate_support(picking)
            group._action_assign()
            locations |= vehicle_location
        self._trip_record_stops(self.picking_ids)
        self.write(
            {
                "date_loaded": fields.Datetime.now(),
                "trip_location_ids": [Command.set(locations.ids)],
                "weight_departure": sum(
                    self.trip_stop_ids.filtered(
                        lambda stop: stop.picking_id in self.picking_ids
                    ).mapped("weight_departure")
                ),
            }
        )
        self._trip_checkpoint(
            "load",
            method="system",
            note=self.env._(
                "%(count)s deliveries, %(weight)s kg.",
                count=len(self.picking_ids),
                weight=round(self.weight_departure, 2),
            ),
        )

    def action_trip_open_load_stock(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Load Stock to Sell"),
            "res_model": "wizard.stock.trip.load.stock",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_batch_id": self.id},
        }

    def _trip_load_free_stock(self, quantities) -> None:
        """Board ``quantities`` no delivery asks for, to be sold from the vehicle.

        :param list quantities: (product, quantity) pairs in the product's unit
        """
        self.check_singleton()
        if self.date_departure:
            raise UserError(
                self.env._("Trip %s has departed: it loads nothing more.", self.name)
            )
        if not self.has_trip_trace or not self.vehicle_id:
            raise UserError(
                self.env._(
                    "Trip %s does not trace its load on a vehicle, so it carries no "
                    "stock to sell.",
                    self.name,
                )
            )
        if not self.date_loaded:
            if self.picking_ids:
                self.action_trip_load()
            else:
                self._check_trip_vehicle_empty()
        picking_type = self.picking_type_id
        source = (
            picking_type.default_location_src_id
            or picking_type.warehouse_id.lot_stock_id
        )
        vehicle_location = source._get_or_create_trip_vehicle_location(self.vehicle_id)
        picking = self._trip_support_picking(source, vehicle_location, "load")
        self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "product_uom_qty": quantity,
                    "location_id": source.id,
                    "location_dest_id": vehicle_location.id,
                    "picking_id": picking.id,
                    "company_id": self.company_id.id,
                    "origin": self.name,
                    "trip_batch_id": self.id,
                    "trip_move_kind": "load",
                }
                for product, quantity in quantities
            ]
        )
        picking.action_confirm()
        picking.action_assign()
        short = picking.move_ids.filtered(lambda move: move.state != "assigned")
        if short:
            raise UserError(
                self.env._(
                    "%(location)s does not hold all of %(products)s to load.",
                    location=source.display_name,
                    products=", ".join(short.product_id.mapped("display_name")),
                )
            )
        self._trip_validate_support(picking)
        vals = {"trip_location_ids": [Command.link(vehicle_location.id)]}
        if not self.date_loaded:
            vals["date_loaded"] = fields.Datetime.now()
        self.write(vals)
        self._trip_checkpoint(
            "load",
            method="system",
            note=self.env._(
                "Stock to sell on the route: %(lines)s.",
                lines=", ".join(
                    f"{quantity:g} {product.display_name}"
                    for product, quantity in quantities
                ),
            ),
        )

    def action_depart(self):
        self.check_singleton()
        if self.has_trip_trace and not self.date_loaded:
            missing = self._trip_departure_missing()
            if missing:
                raise UserError(
                    self.env._(
                        "Trip %(batch)s cannot depart, it is missing: %(fields)s.",
                        batch=self.name,
                        fields=", ".join(missing),
                    )
                )
            self.action_trip_load()
        res = super().action_depart()
        self._trip_checkpoint(
            "departure",
            odometer=self.odometer_departure,
            fuel_level=self.fuel_departure,
            employee_id=self.operator_id.id,
        )
        return res

    def action_return(self):
        self.check_singleton()
        self._check_trip_offline_events_resolved()
        self._check_trip_offline_phone_head()
        if (
            self.has_trip_trace
            and self.date_departure
            and not self.date_return
            and not self.fuel_return
        ):
            raise UserError(self.env._("The fuel at return is not set."))
        res = super(
            StockPickingBatch, self.with_context(trip_returning=True)
        ).action_return()
        self._trip_checkpoint(
            "return",
            odometer=self.odometer_return,
            fuel_level=self.fuel_return,
        )
        if self.date_loaded:
            self._trip_create_unload()
        return res

    def action_trip_unload(self):
        """Take the goods off a loaded trip that will not leave."""
        self.check_singleton()
        if not self.date_loaded or self.date_departure:
            raise UserError(
                self.env._(
                    "Only a loaded trip that has not departed is unloaded this way; "
                    "a departed one is unloaded on its return."
                )
            )
        self._trip_create_unload()
        return self.action_trip_open_unload()

    def _trip_create_unload(self):
        """Prepare the unloading of what is left on the vehicle.

        Goods a delivery still holds go back to where deliveries leave from, still
        reserved to it; everything else goes to the warehouse stock. The warehouse
        confirms the quantities it counts.
        """
        self.check_singleton()
        warehouse = self.picking_type_id.warehouse_id
        pickings = self.env["stock.picking"]
        loaded = {
            location
            for [location] in self.env["stock.quant"]._read_group(
                [
                    ("location_id", "in", self.trip_location_ids.ids),
                    ("quantity", ">", 0),
                ],
                ["location_id"],
            )
        }
        for location in self.trip_location_ids:
            if location not in loaded:
                continue
            picking = self._trip_support_picking(
                location, warehouse.lot_stock_id, "unload"
            )
            pending = self._trip_pending_delivery_moves(location)
            self._trip_reroute(pending, location.location_id, "unload", picking)
            self._trip_move_free_goods(
                location, warehouse.lot_stock_id, "unload", picking
            )
            pickings |= picking
        if pickings:
            self.write(
                {"unload_picking_id": pickings[:1].id, "balance_state": "pending"}
            )
            self._trip_notify_unload(pickings)
        else:
            self._trip_compute_balance()
        return pickings

    def _trip_notify_unload(self, pickings) -> None:
        self.check_singleton()
        user = self.supervisor_id or self.env.user
        for picking in pickings:
            picking.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=self.env._("Confirm the unloading of trip %s", self.name),
                note=self.env._(
                    "Count what came back on the vehicle and validate: the "
                    "quantities you confirm close the trip's balance."
                ),
            )

    def action_trip_open_unload(self):
        self.check_singleton()
        pickings = self.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "stock.action_picking_tree_all"
        )
        action["domain"] = [("id", "in", pickings.ids)]
        if len(pickings) == 1:
            action.update({"views": [(False, "form")], "res_id": pickings.id})
        return action

    def _trip_after_unload(self) -> None:
        """The warehouse confirmed an unloading: rebind deliveries, reconcile."""
        self.check_singleton()
        self._check_trip_offline_events_resolved()
        self._check_trip_partial_review_resolved()
        unloads = self.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        unloads.move_ids.move_dest_ids.filtered(
            lambda m: m.state not in ("done", "cancel")
        )._action_assign()
        if all(p.state in ("done", "cancel") for p in unloads):
            self._trip_checkpoint("unload", method="system")
            self._trip_compute_balance()

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------
    def _trip_compute_balance(self):
        """Rebuild the balance from the trip's done movements."""
        self.check_singleton()
        Line = self.env["stock.move.line"]
        rows = defaultdict(lambda: defaultdict(float))

        def add(lines, column):
            for line in lines:
                rows[(line.product_id, line.trace_id)][column] += (
                    line.quantity_product_uom
                )

        done = [("state", "=", "done")]
        add(
            Line.search(
                [
                    *done,
                    ("move_id.trip_batch_id", "=", self.id),
                    ("move_id.trip_move_kind", "=", "load"),
                ]
            ),
            "qty_loaded",
        )
        add(
            Line.search(
                [
                    *done,
                    ("move_id.trip_target_batch_id", "=", self.id),
                    ("move_id.trip_move_kind", "=", "handover"),
                ]
            ),
            "qty_received",
        )
        add(
            Line.search(
                [
                    *done,
                    ("move_id.trip_batch_id", "=", self.id),
                    ("move_id.trip_move_kind", "=", "handover"),
                ]
            ),
            "qty_handed_over",
        )
        add(
            Line.search(
                [
                    *done,
                    ("move_id.trip_batch_id", "=", self.id),
                    ("move_id.trip_move_kind", "=", "delivery"),
                    ("location_id", "in", self.trip_location_ids.ids),
                ]
            ),
            "qty_delivered",
        )
        add(
            Line.search(
                [
                    *done,
                    ("move_id.trip_batch_id", "=", self.id),
                    ("move_id.trip_move_kind", "=", "write_off"),
                ]
            ),
            "qty_written_off",
        )
        add(
            Line.search(
                [
                    *done,
                    ("move_id.trip_batch_id", "=", self.id),
                    ("move_id.trip_move_kind", "=", "unload"),
                ]
            ),
            "qty_returned",
        )
        Balance = self.env["stock.trip.balance"].with_privilege(
            "stock_fleet_trace.privilege_trip_trace_record",
            reason="a trip rebuilds its own balance",
        )
        Balance.browse(self.trip_balance_ids.ids).unlink()
        lines = Balance.create(
            [
                {
                    "batch_id": self.id,
                    "product_id": product.id,
                    "trace_id": lot.id,
                    **qty,
                }
                for (product, lot), qty in rows.items()
            ]
        )
        unloaded = not self.unload_picking_id or self.unload_picking_id.state == "done"
        if not self.date_return or not unloaded:
            state = "pending"
        elif all(
            float_is_zero(line.qty_difference, precision_rounding=line.uom_id.rounding)
            for line in lines
        ):
            state = "balanced"
        else:
            state = "difference"
        self.balance_state = state
        if state == "difference":
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=(self.supervisor_id or self.env.user).id,
                summary=self.env._("Trip %s does not balance", self.name),
                note=self.env._(
                    "What came back differs from what the trip should have brought "
                    "back. Review the Balance tab."
                ),
            )
        return lines

    def action_trip_compute_balance(self) -> None:
        for batch in self:
            batch._trip_compute_balance()

    # ------------------------------------------------------------------
    # Handover after a breakdown
    # ------------------------------------------------------------------
    def _trip_handover(self, target) -> None:
        """Move this trip's pending deliveries and load onto ``target``'s vehicle.

        :param recordset target: a trip that has not departed, on another vehicle
        """
        self.check_singleton()
        pending = self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))
        locations = self.env["stock.location"]
        for location in self.trip_location_ids:
            destination = location.location_id._get_or_create_trip_vehicle_location(
                target.vehicle_id
            )
            picking = self._trip_support_picking(location, destination, "handover")
            moves = self._trip_pending_delivery_moves(location)
            self._trip_reroute(moves, destination, "handover", picking, target=target)
            self._trip_move_free_goods(
                location, destination, "handover", picking, target=target
            )
            if picking.move_ids:
                self._trip_validate_support(picking)
                moves._action_assign()
                locations |= destination
            else:
                picking.unlink()
        pending.move_ids.filtered(lambda m: m.trip_batch_id == self).write(
            {"trip_batch_id": target.id}
        )
        pending.with_context(**{UNBATCH_UNDELIVERED: True, MERGE_TRIPS: True}).write(
            {"batch_id": target.id}
        )
        target.write(
            {
                "date_loaded": fields.Datetime.now(),
                "trip_location_ids": [Command.set(locations.ids)],
                "weight_departure": target._trip_weight_on_board_of(locations),
                "handover_from_batch_id": self.id,
            }
        )
        target._trip_record_stops(pending)
        self.weight_free_handed_over = target.weight_departure - sum(
            target.trip_stop_ids.mapped("weight_departure")
        )
        self._trip_checkpoint(
            "handover",
            method="system",
            note=self.env._(
                "%(count)s deliveries handed over to trip %(target)s (%(vehicle)s).",
                count=len(pending),
                target=target.name,
                vehicle=target.vehicle_id.display_name,
            ),
        )
        target._trip_checkpoint(
            "load",
            method="system",
            note=self.env._("Taken over from trip %s.", self.name),
        )

    def _trip_weight_on_board_of(self, locations):
        """What the goods in ``locations`` weigh, without pallets or packaging.

        :rtype: float
        """
        return sum(
            q.product_id._trip_weight(q.quantity)
            for q in self._trip_quants_in(locations)
        )

    def action_trip_open_handover(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Hand the load over"),
            "res_model": "wizard.stock.trip.handover",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_batch_id": self.id},
        }

    def action_trip_new_incident(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Report an incident"),
            "res_model": "stock.trip.incident",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_batch_id": self.id},
        }

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------
    def action_trip_open_scan(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Scan"),
            "res_model": "wizard.stock.trip.scan",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_batch_id": self.id},
        }

    def _trip_process_scan(self, code, quantity=None, picking=None) -> tuple:
        """Act on a scanned code: the trip sheet, a delivery slip or a lot label.

        One scan counts in full: a slip registers every unit of its delivery,
        a lot label every unit of that lot still unscanned at the stop.

        :param str code: what the scanner read
        :param float quantity: units one lot scan counts; empty for all of them
        :param recordset picking: the stop whose slip was scanned last
        :return: a message for the person scanning, and the current stop
        :rtype: tuple
        """
        self.check_singleton()
        code = (code or "").strip()
        picking = picking or self.env["stock.picking"]
        Scan = self.env["stock.trip.scan"]
        if code == self.name:
            return self._trip_scan_sheet(), picking
        stop = self.picking_ids.filtered(lambda p: p.name == code)
        if stop:
            return self._trip_scan_stop(stop), stop
        lots = self.env["product.trace"].search([("name", "=", code)])
        if lots:
            if not picking:
                raise UserError(
                    self.env._("Scan the delivery slip of the stop before its lots.")
                )
            on_board = picking._trip_on_board_by_lot()
            lot = lots.filtered(lambda lot: (lot.product_id, lot) in on_board)[:1]
            if not lot:
                raise UserError(
                    self.env._(
                        "Lot %(lot)s does not travel for %(stop)s. Check the product "
                        "before handing it over.",
                        lot=code,
                        stop=picking.name,
                    )
                )
            key = (lot.product_id, lot)
            already = picking._trip_scanned_by_lot().get(key, 0.0)
            if not quantity:
                quantity = on_board[key] - already
                if quantity <= 0:
                    return (
                        self.env._(
                            "%(product)s lot %(lot)s: already complete, %(board)s "
                            "of %(board)s.",
                            product=lot.product_id.display_name,
                            lot=lot.name,
                            board=on_board[key],
                        ),
                        picking,
                    )
            scanned = already + quantity
            if scanned > on_board[key]:
                raise UserError(
                    self.env._(
                        "%(product)s: %(scanned)s scanned but only %(board)s travel "
                        "for %(stop)s.",
                        product=lot.product_id.display_name,
                        scanned=scanned,
                        board=on_board[key],
                        stop=picking.name,
                    )
                )
            Scan.create(
                {
                    "batch_id": self.id,
                    "picking_id": picking.id,
                    "code": code,
                    "kind": "lot",
                    "product_id": lot.product_id.id,
                    "trace_id": lot.id,
                    "quantity": quantity,
                }
            )
            return (
                self.env._(
                    "%(product)s lot %(lot)s: %(scanned)s of %(board)s.",
                    product=lot.product_id.display_name,
                    lot=lot.name,
                    scanned=scanned,
                    board=on_board[key],
                ),
                picking,
            )
        raise UserError(
            self.env._(
                "Code %(code)s is not this trip's sheet, one of its deliveries nor a "
                "lot it carries.",
                code=code,
            )
        )

    def _trip_scan_sheet(self) -> str:
        """The trip sheet read at the warehouse: departure or return."""
        self.env["stock.trip.scan"].create(
            {"batch_id": self.id, "code": self.name, "kind": "trip_sheet"}
        )
        has_gps = "gps_device_id" in self.vehicle_id._fields and bool(
            self.vehicle_id.gps_device_id
        )
        barcode = self.with_context(trip_checkpoint_method="barcode")
        if not self.date_departure:
            if not self.date_loaded:
                raise UserError(
                    self.env._("Trip %s is not loaded yet: load it first.", self.name)
                )
            if has_gps:
                barcode._trip_checkpoint(
                    "scan", note=self.env._("Sheet read at departure.")
                )
                return self.env._(
                    "Sheet read. The GPS stamps the departure when the vehicle leaves."
                )
            barcode.action_depart()
            return self.env._("Trip %s departed.", self.name)
        if not self.date_return:
            if has_gps:
                barcode._trip_checkpoint(
                    "scan", note=self.env._("Sheet read at return.")
                )
                return self.env._(
                    "Sheet read. The GPS stamps the return when the vehicle arrives."
                )
            barcode.action_return()
            return self.env._("Trip %s closed.", self.name)
        return self.env._("Trip %s is already closed.", self.name)

    def _trip_scan_stop(self, stop) -> str:
        """A delivery slip read at the customer: the arrival, if not yet known,
        and every unit of the delivery registered in one scan."""
        if not self.date_departure:
            raise UserError(self.env._("Trip %s has not departed yet.", self.name))
        Scan = self.env["stock.trip.scan"]
        Scan.create(
            {
                "batch_id": self.id,
                "picking_id": stop.id,
                "code": stop.name,
                "kind": "delivery",
            }
        )
        if not stop.trip_arrival_date:
            stop.trip_arrival_date = fields.Datetime.now()
            self.with_context(trip_checkpoint_method="barcode")._trip_checkpoint(
                "arrival", picking_id=stop.id
            )
        scanned = stop._trip_scanned_by_lot()
        missing = [
            (product, lot, quantity - scanned.get((product, lot), 0.0))
            for (product, lot), quantity in stop._trip_on_board_by_lot().items()
            if quantity - scanned.get((product, lot), 0.0) > 0
        ]
        Scan.create(
            [
                {
                    "batch_id": self.id,
                    "picking_id": stop.id,
                    "code": stop.name,
                    "kind": "lot",
                    "product_id": product.id,
                    "trace_id": lot.id,
                    "quantity": quantity,
                }
                for product, lot, quantity in missing
            ]
        )
        return self.env._(
            "%(stop)s (%(customer)s): %(units)s units registered. Scan a lot "
            "label only to check it.",
            stop=stop.name,
            customer=stop.partner_id.display_name,
            units=sum(stop._trip_on_board_by_lot().values()),
        )
