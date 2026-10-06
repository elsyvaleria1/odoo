from odoo import fields, models
from odoo.tools import float_compare, float_is_zero

# Differences below this many kilograms are rounding, not goods.
WEIGHT_PRECISION = 2


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    trip_handover_to_ids = fields.One2many(
        comodel_name="stock.picking.batch",
        inverse_name="handover_from_batch_id",
        string="Handed Over To",
        help="Rescue trips that took over this trip's load after a breakdown.",
    )
    trip_stop_ids = fields.One2many(
        comodel_name="stock.trip.stop",
        inverse_name="batch_id",
        string="Delivery Weights",
    )
    weight_free_handed_over = fields.Float(
        string="Free Weight Handed Over",
        digits="Stock Weight",
        copy=False,
        readonly=True,
        help="Theoretical weight of the goods nobody reserved (rejections) that a "
        "breakdown moved to the rescue trip.",
    )

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def _trip_record_stops(self, pickings):
        """Freeze what each delivery weighs as it boards this trip.

        :param recordset pickings: the deliveries boarding, with their goods
            already reserved on the vehicle
        """
        self.check_singleton()
        Stop = self.env["stock.trip.stop"].with_privilege(
            "stock_fleet_trace.privilege_trip_trace_record",
            reason="a trip records what each delivery weighed",
        )
        known = {stop.picking_id: stop for stop in self.trip_stop_ids}
        for picking in pickings:
            vals = {
                "weight_departure": picking._trip_goods_weight(),
                "sequence": picking.batch_sequence,
            }
            if picking in known:
                Stop.browse(known[picking].id).write(vals)
            else:
                Stop.create({**vals, "batch_id": self.id, "picking_id": picking.id})

    def _trip_record_written_off(self, picking, weight):
        """Charge ``weight`` lost on the route to ``picking`` on this trip."""
        self.check_singleton()
        stop = self.trip_stop_ids.filtered(lambda s: s.picking_id == picking)
        if stop:
            stop.with_privilege(
                "stock_fleet_trace.privilege_trip_trace_record",
                reason="a trip records what each delivery lost",
            ).weight_written_off += weight

    # ------------------------------------------------------------------
    # Trip sheet
    # ------------------------------------------------------------------
    def _trip_report_stops(self):
        """Every delivery this trip carried, with its weight and where it ended.

        Read from what each delivery weighed when it boarded this trip, so later
        trips of the same delivery do not change this one's sheet.

        :return: per delivery (``picking`` False for goods nobody reserved) its
            outcome and the weight at departure, delivered, written off, handed
            over and brought back
        :rtype: list
        """
        self.check_singleton()
        checkpoints = self.trip_checkpoint_ids
        delivered_here = checkpoints.filtered(
            lambda c: c.event_type == "delivery"
        ).picking_id
        not_delivered_here = checkpoints.filtered(
            lambda c: c.event_type == "not_delivered"
        ).picking_id
        rejected = {}
        for checkpoint in checkpoints.filtered(lambda c: c.event_type == "rejection"):
            rejected[checkpoint.picking_id] = rejected.get(
                checkpoint.picking_id, 0.0
            ) + checkpoint.product_id._trip_weight(checkpoint.quantity)
        rescue_of = {
            stop.picking_id: stop for stop in self.trip_handover_to_ids.trip_stop_ids
        }
        outcomes = dict(
            self.env["stock.picking"]
            ._fields["trip_delivery_result"]
            ._description_selection(self.env)
        )
        stops = []
        for stop in self.trip_stop_ids:
            picking = stop.picking_id
            row = {
                "picking": picking,
                "departure": stop.weight_departure,
                "delivered": 0.0,
                "written_off": stop.weight_written_off,
                "handed_over": 0.0,
                "rejected": rejected.get(picking, 0.0),
            }
            if picking in rescue_of:
                rescue_stop = rescue_of[picking]
                row["outcome"] = self.env._(
                    "Handed over to %s", rescue_stop.batch_id.name
                )
                row["handed_over"] = rescue_stop.weight_departure
            elif picking in not_delivered_here:
                row["outcome"] = outcomes["not_delivered"]
            elif picking in delivered_here:
                row["delivered"] = picking.move_ids.move_line_ids.filtered(
                    lambda line: line.state == "done"
                )._trip_goods_weight()
                row["outcome"] = (
                    outcomes.get(picking.trip_delivery_result) or (outcomes["complete"])
                )
            else:
                row["outcome"] = self.env._("On board")
            row["back"] = (
                row["departure"]
                - row["delivered"]
                - row["written_off"]
                - row["handed_over"]
            )
            stops.append(row)
        self._trip_report_free_goods(stops)
        return stops

    def _trip_report_free_goods(self, stops):
        """Account for the goods nobody reserved: rejections and what a rescue took.

        Rejected goods stay on the vehicle, free. A write-off of free goods and
        the free goods a breakdown moved to the rescue come out of the rejecting
        deliveries first; what is left, and what a rescue trip took over free,
        gets its own row.
        """
        written_off = self.trip_incident_ids.filtered(
            lambda i: i.state == "approved"
        ).line_ids._trip_goods_weight()
        free_lost = written_off - sum(self.trip_stop_ids.mapped("weight_written_off"))
        free_moved = self.weight_free_handed_over
        for key, amount in (("written_off", free_lost), ("handed_over", free_moved)):
            for row in sorted(stops, key=lambda r: -r["rejected"]):
                if amount <= 0:
                    break
                taken = min(amount, row["rejected"], max(row["back"], 0.0))
                row[key] += taken
                row["back"] -= taken
                row["rejected"] -= taken
                amount -= taken
            if key == "written_off":
                free_lost = amount
            else:
                free_moved = amount
        free_in = 0.0
        if self.handover_from_batch_id:
            free_in = self.weight_departure - sum(
                self.trip_stop_ids.mapped("weight_departure")
            )
        if any(
            not float_is_zero(value, precision_digits=WEIGHT_PRECISION)
            for value in (free_in, free_lost, free_moved)
        ):
            stops.append(
                {
                    "picking": self.env["stock.picking"],
                    "outcome": self.env._("Goods nobody reserved (rejections)"),
                    "departure": free_in,
                    "delivered": 0.0,
                    "written_off": free_lost,
                    "handed_over": free_moved,
                    "rejected": 0.0,
                    "back": free_in - free_lost - free_moved,
                }
            )

    def _trip_report_weights_match(self, stops) -> bool:
        """Whether the deliveries' weights add up to the trip's, row by row too.

        :rtype: bool
        """
        self.check_singleton()
        total = sum(stop["departure"] for stop in stops)
        if float_compare(total, self.weight_departure, precision_digits=2):
            return False
        return all(
            float_compare(stop["back"], 0.0, precision_digits=WEIGHT_PRECISION) >= 0
            for stop in stops
        )

    def _trip_report_handover_lines(self, rescue):
        """The goods a breakdown moved to ``rescue``, as the handover moved them.

        :return: per moved line its delivery (empty for free goods), product,
            lot, quantity and unit
        :rtype: list
        """
        self.check_singleton()
        moves = self.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "handover"
        ).move_ids.filtered(lambda m: m.trip_target_batch_id == rescue)
        lines = [
            {
                "picking": move.move_dest_ids.picking_id[:1],
                "product": line.product_id,
                "lot": line.trace_id,
                "quantity": line.quantity,
                "uom": line.product_uom_id,
            }
            for move in moves
            for line in move.move_line_ids
        ]
        return sorted(
            lines,
            key=lambda line: (line["picking"].batch_sequence, line["picking"].id or 0),
        )

    def _trip_report_breakdown(self, rescue):
        """The breakdown that sent ``rescue``: the one linked, else the latest."""
        self.check_singleton()
        breakdowns = self.trip_incident_ids.filtered(
            lambda i: i.incident_type == "breakdown" and i.state == "approved"
        )
        linked = breakdowns.filtered(lambda i: i.trip_rescue_batch_id == rescue)
        return linked[:1] or breakdowns.sorted("date", reverse=True)[:1]

    def _trip_report_write_offs(self):
        """What approved incidents took off the vehicle, line by line.

        :return: per lost line its incident, delivery, product, lot, quantity,
            weight and the scrap that took it off the stock
        :rtype: list
        """
        self.check_singleton()
        kinds = dict(
            self.env["stock.trip.incident"]
            ._fields["incident_type"]
            ._description_selection(self.env)
        )
        rows = []
        for incident in self.trip_incident_ids.filtered(
            lambda i: i.state == "approved"
        ).sorted("date"):
            for line in incident.line_ids:
                scrap = incident.scrap_ids.filtered(
                    lambda sc, ln=line: (
                        sc.product_id == ln.product_id and sc.trace_id == ln.trace_id
                    )
                )[:1]
                rows.append(
                    {
                        "incident": incident,
                        "kind": kinds.get(incident.incident_type, ""),
                        "picking": line.picking_id,
                        "product": line.product_id,
                        "lot": line.trace_id,
                        "quantity": line.quantity,
                        "uom": line.product_id.uom_id,
                        "weight": line._trip_goods_weight(),
                        "scrap": scrap,
                    }
                )
        return rows

    def _trip_report_movements(self):
        """The stock moves the trip made: loading, handover, unloading, write-offs.

        :return: per transfer or scrap its reference, what it was, from, to,
            state and date
        :rtype: list
        """
        self.check_singleton()
        kinds = dict(
            self.env["stock.picking"]
            ._fields["trip_support_kind"]
            ._description_selection(self.env)
        )
        states = dict(
            self.env["stock.picking"]._fields["state"]._description_selection(self.env)
        )
        rows = [
            {
                "reference": picking.name,
                "kind": kinds.get(picking.trip_support_kind, ""),
                "source": picking.location_id.display_name,
                "destination": picking.location_dest_id.display_name,
                "state": states.get(picking.state, picking.state),
                "date": picking.date_done or picking.scheduled_date,
            }
            for picking in self.trip_support_picking_ids.sorted("id")
        ]
        scrap_label = self.env._("Write-off")
        scrap_states = dict(
            self.env["stock.scrap"]._fields["state"]._description_selection(self.env)
        )
        rows.extend(
            {
                "reference": scrap.name,
                "kind": scrap_label,
                "source": scrap.location_id.display_name,
                "destination": scrap.scrap_location_id.display_name,
                "state": scrap_states.get(scrap.state, scrap.state),
                "date": scrap.date_done,
            }
            for scrap in self.trip_incident_ids.scrap_ids.sorted("id")
        )
        return rows

    def _trip_report_rescue_outcomes(self, rescue):
        """What happened on ``rescue`` to each delivery it took over.

        :rtype: dict
        """
        self.check_singleton()
        return {
            row["picking"]: row["outcome"]
            for row in rescue._trip_report_stops()
            if row["picking"]
        }
