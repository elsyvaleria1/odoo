from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    trip_return_leg_km = fields.Float(
        string="Return leg km (GPS)",
        digits=(16, 1),
        copy=False,
        readonly=True,
        help="Kilometres from the last delivery back to the warehouse, from the GPS.",
    )
    trip_gps_km = fields.Float(
        string="Trip km (GPS)",
        digits=(16, 1),
        copy=False,
        readonly=True,
        help="Kilometres of every leg of the trip, return included, from the GPS.",
    )

    def action_read_gps_odometer_departure(self) -> None:
        """Fill the departure odometer from the vehicle's GPS before the trip leaves."""
        self.check_singleton()
        if self.date_departure:
            raise UserError(self.env._("Trip %s has already departed.", self.name))
        self.odometer_departure = self._require_vehicle().resource_id.get_current_odometer()

    def action_read_gps_odometer_return(self) -> None:
        """Fill the return odometer from the vehicle's GPS before closing the trip."""
        self.check_singleton()
        if self.date_return:
            raise UserError(self.env._("Trip %s is already closed.", self.name))
        self.odometer_return = self._require_vehicle().resource_id.get_current_odometer()

    def _require_vehicle(self):
        if not self.vehicle_id:
            raise UserError(self.env._("Trip %s has no vehicle.", self.name))
        return self.vehicle_id

    def action_return(self):
        res = super().action_return()
        # The GPS has sent the whole route by the time the vehicle is back; a vehicle
        # without one closes its trip all the same.
        if self.vehicle_id.gps_device_id:
            self._capture_gps_legs()
        return res

    def action_capture_gps_legs(self) -> None:
        """Read again the kilometres of each leg, for GPS data that arrived late."""
        self.check_singleton()
        if not self.date_departure:
            raise UserError(self.env._("Trip %s has not departed yet.", self.name))
        if not self.vehicle_id.gps_device_id:
            raise UserError(
                self.env._(
                    "Vehicle %s has no GPS device; its kilometres cannot be read.",
                    self.vehicle_id.display_name,
                )
            )
        self._capture_gps_legs()

    def _capture_gps_legs(self) -> None:
        """Give each stop the kilometres of its leg, in the order it was made.

        The first leg starts at the departure and each next one where the
        previous stop ended, so the legs and the return add up to the trip. The
        leg goes to the first delivery of its stop; the others at the same
        address drove no further.
        """
        self.check_singleton()
        start = self.date_departure
        legs = []
        stops = self._gps_leg_stops()
        # A delivery no stop took (the track missed it) keeps no km from an
        # earlier capture: its leg is folded into the next stop's.
        self.picking_ids.union(*(stop["pickings"] for stop in stops)).trip_leg_km = 0.0
        for stop in stops:
            km = self._gps_km_between(start, stop["departure"])
            stop["pickings"][:1].trip_leg_km = km
            legs.append((stop["pickings"], km))
            start = stop["departure"]
        return_km = (
            self._gps_km_between(start, self.date_return) if self.date_return else 0.0
        )
        total = sum(km for _pickings, km in legs) + return_km
        self.write({"trip_return_leg_km": return_km, "trip_gps_km": total})
        _debug.logic(
            "trip_gps_legs",
            batch=self,
            legs=len(legs),
            return_km=return_km,
            total=total,
        )
        self.message_post(
            body=self.env._(
                "Kilometres from the GPS: %(legs)s; return %(back)s km; trip %(total)s km.",
                legs=", ".join(
                    f"{' + '.join(pickings.mapped('name'))} {km:.1f} km"
                    for pickings, km in legs
                )
                or "-",
                back=f"{return_km:.1f}",
                total=f"{total:.1f}",
            )
        )

    def _gps_leg_stops(self):
        """The stops of the trip, in the order the vehicle made them.

        Without a better source, a stop is the validation of its deliveries:
        consecutive deliveries to one address are one stop, from the first
        validation to the last. Modules that know where the vehicle stood
        (its GPS track) override it.

        :return: dicts with ``arrival``, ``departure`` and ``pickings``
        :rtype: list
        """
        self.check_singleton()
        delivered = self.picking_ids.filtered(
            lambda picking: (
                picking.state == "done"
                and picking.date_done
                and picking.date_done >= self.date_departure
            )
        ).sorted(lambda picking: (picking.date_done, picking.id))
        return self._gps_group_stops(
            [(picking, picking.date_done, picking.date_done) for picking in delivered]
        )

    @api.model
    def _gps_group_stops(self, visits):
        """Merge consecutive visits to one delivery address into one stop.

        :param list visits: ``(picking, arrival, departure)`` in the order made
        :return: dicts with ``arrival``, ``departure`` and ``pickings``
        :rtype: list
        """
        stops = []
        for picking, arrival, departure in visits:
            last = stops[-1] if stops else None
            address = picking.partner_id
            if last and address and last["pickings"][:1].partner_id == address:
                last["pickings"] |= picking
                last["departure"] = max(last["departure"], departure)
                continue
            stops.append(
                {"arrival": arrival, "departure": departure, "pickings": picking}
            )
        return stops

    def _gps_km_between(self, date_from, date_to):
        """Kilometres the trip's vehicle moved between two moments.

        The odometer difference when a recent reading stands at or before both
        moments, so the legs add up to the trip; otherwise the distance between
        its positions.

        :rtype: float
        """
        vehicle = self.vehicle_id.resource_id
        # The last reading at or before a moment, not the closest on either side:
        # a tracker goes quiet with the engine off, and the odometer does not move
        # while it is.
        max_age = vehicle._trip_reading_max_age()
        start = vehicle._gps_odometer_reading(date_from, before=max_age)
        end = vehicle._gps_odometer_reading(date_to, before=max_age)
        if start and end and end.value >= start.value:
            return end.value - start.value
        # trail_points reads the logs under its own elevation
        logs = vehicle.env["device.data.log.gps"]
        analytics = logs.trail_analytics(
            logs.trail_points([vehicle.gps_device_id.id], date_from, date_to)
        )
        _debug.logic(
            "trip_gps_leg_by_positions",
            batch=self,
            date_from=date_from,
            date_to=date_to,
        )
        return analytics.get("distance_gps", 0.0)
