from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    trip_delivery_result = fields.Selection(
        selection=[
            ("complete", "Complete"),
            ("partial", "Partial"),
            ("not_delivered", "Not delivered"),
        ],
        string="Delivery Result",
        index="btree_not_null",
        copy=False,
        tracking=True,
    )
    trip_arrival_date = fields.Datetime(
        string="Arrival",
        copy=False,
        help="When the vehicle reached the customer.",
    )
    trip_support_batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip Served",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Trip this transfer loads, unloads or hands over.",
    )
    trip_support_kind = fields.Selection(
        selection=[
            ("load", "Loading"),
            ("handover", "Handover"),
            ("unload", "Unloading"),
        ],
        copy=False,
        readonly=True,
    )
    trip_partial_review = fields.Boolean(
        string="Partial Delivery to Review",
        copy=False,
        help="Captured offline without quantities: the supervisor confirms what "
        "the customer took with the Partial wizard, which clears this flag. The "
        "trip's unloading is not validated while it is set.",
    )
    trip_receiver_name = fields.Char(
        string="Received By",
        copy=False,
        help="Who took the goods, as given by the driver's phone or app.",
    )

    def button_validate(self, **validate_kwargs):
        if self and all(self.mapped(lambda p: p._trip_expiry_decided())):
            self = self.with_context(skip_expired=True)
        return super().button_validate(**validate_kwargs)

    def _trip_expiry_decided(self):
        self.check_singleton()
        trip = self.batch_id
        picking_type = self.picking_type_id
        return bool(
            self.picking_type_code == "outgoing"
            and trip.has_trip_trace
            and trip.date_loaded
            and trip.date_departure
            and not trip.date_return
            and picking_type._fields.get("block_expired_lots")
            and picking_type.block_expired_lots
            and self.move_line_ids
            and all(
                line.location_id in trip.trip_location_ids
                for line in self.move_line_ids
            )
        )

    def _take_off_trip_as_correction(self, reason):
        on_board = self.filtered(
            lambda picking: (
                picking.batch_id.has_trip_trace
                and picking.move_line_ids.filtered(
                    lambda line: line.location_id in picking.batch_id.trip_location_ids
                )
            )
        )
        if on_board:
            raise UserError(
                self.env._(
                    "%(pickings)s already travel on the vehicle of trip %(batch)s: "
                    "register them as not delivered, with their reason, so their "
                    "goods come back with the unload.",
                    pickings=", ".join(on_board.mapped("name")),
                    batch=on_board.batch_id[:1].name,
                )
            )
        return super()._take_off_trip_as_correction(reason)

    def action_trip_view_signature(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Signature of %s", self.name),
            "res_model": "stock.picking",
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "stock_fleet_trace.stock_picking_view_form_signature"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
        }

    def _requires_trip(self):
        if self.env.context.get("trip_returning") and self.trip_partial_review:
            return False
        return super()._requires_trip()

    def _trip_location(self):
        self.check_singleton()
        for partner in (self.partner_id, self.partner_id.commercial_partner_id):
            if partner.partner_latitude or partner.partner_longitude:
                return partner.partner_latitude, partner.partner_longitude
        return None

    def _trip_goods_weight(self):
        self.check_singleton()
        return self.move_ids.move_line_ids.filtered(
            lambda line: line.state not in ("done", "cancel")
        )._trip_goods_weight()

    def write(self, vals):
        if "batch_id" in vals:
            trip = self.env["stock.picking.batch"].browse(vals["batch_id"])
            if trip.date_loaded and not trip.date_departure:
                trip._check_trip_loaded_takes_no_new_pickings(
                    self.filtered(lambda p: p.batch_id != trip)
                )
            for current, leaving in (
                self.filtered(
                    lambda p: (
                        p.batch_id != trip
                        and p.batch_id.date_loaded
                        and not p.batch_id.date_departure
                    )
                )
                .grouped("batch_id")
                .items()
            ):
                current._check_trip_loaded_keeps_its_pickings(leaving)
        return super().write(vals)

    def action_trip_arrived(self) -> None:
        self.check_singleton()
        if not self.batch_id.date_departure:
            raise UserError(
                self.env._("Transfer %s is not on a trip that has departed.", self.name)
            )
        self.trip_arrival_date = fields.Datetime.now()
        self.batch_id._trip_checkpoint("arrival", picking_id=self.id)

    def action_trip_stop_result(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Stop result"),
            "res_model": "wizard.stock.trip.stop.result",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {"default_picking_id": self.id},
        }

    def action_deliver(self):
        self.check_singleton()
        if self.trip_scan_ids.filtered(
            lambda s: s.kind == "lot" and s.batch_id == self.batch_id
        ):
            scanned = self._trip_scanned_by_lot()
            on_board = self._trip_on_board_by_lot()
            if any(
                scanned.get(key, 0.0) != qty
                for key, qty in on_board.items()
                if key[1] or key in scanned
            ):
                raise UserError(
                    self.env._(
                        "What was scanned at %(name)s does not match what the vehicle "
                        "carries for it:\n%(summary)s\nUse Partial.",
                        name=self.name,
                        summary=self._trip_scan_summary(),
                    )
                )
        return super().action_deliver()

    def _register_delivery_failure(self, reason):
        batch = self.batch_id
        if batch:
            batch._trip_checkpoint(
                "not_delivered",
                picking_id=self.id,
                reason_id=self.delivery_failure_reason_id.id,
                note=reason,
            )
        res = super()._register_delivery_failure(reason)
        self.trip_delivery_result = "not_delivered"
        return res

    def _action_done(self, *, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        self._trip_record_outcome()
        for batch in self.filtered(
            lambda p: p.trip_support_kind == "unload" and p.state == "done"
        ).trip_support_batch_id:
            batch._trip_after_unload()
        return res

    def _trip_record_outcome(self) -> None:
        for picking in self.filtered(
            lambda p: (
                p.state == "done"
                and p.picking_type_code == "outgoing"
                and p.batch_id.date_departure
            )
        ):
            batch = picking.batch_id
            if batch.trip_checkpoint_ids.filtered(
                lambda c, p=picking: c.event_type == "delivery" and c.picking_id == p
            ):
                continue
            result = self.env.context.get("trip_delivery_result") or (
                "partial" if picking.backorder_ids else "complete"
            )
            picking.trip_delivery_result = result
            batch._trip_checkpoint(
                "delivery",
                picking_id=picking.id,
                note=result,
                method="barcode" if picking.trip_scan_ids else "manual",
            )
