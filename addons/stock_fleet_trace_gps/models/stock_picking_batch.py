import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.device_gps.tools import haversine_m

_logger = logging.getLogger(__name__)

HARSH_DRIVING_EVENT = "253"
STANDING_SPEED = 3.0
FIRST_READ_WINDOW = timedelta(days=1)


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    trip_gps_exit_date = fields.Datetime(
        string="Left Warehouse (GPS)",
        copy=False,
        readonly=True,
    )
    trip_gps_entry_date = fields.Datetime(
        string="Back at Warehouse (GPS)",
        copy=False,
        readonly=True,
    )
    trip_harsh_event_count = fields.Integer(
        string="Harsh Driving Events",
        copy=False,
        readonly=True,
    )
    trip_alert_ids = fields.One2many(
        comodel_name="stock.trip.alert",
        inverse_name="batch_id",
        string="Alerts",
    )
    trip_alert_open_count = fields.Integer(
        string="Open Alerts",
        compute="_compute_trip_alert_open_count",
    )
    has_trip_gps = fields.Boolean(compute="_compute_has_trip_gps")

    @api.depends("trip_alert_ids.state")
    def _compute_trip_alert_open_count(self) -> None:
        for batch in self:
            batch.trip_alert_open_count = len(
                batch.trip_alert_ids.filtered(lambda a: a.state == "open")
            )

    @api.depends("vehicle_id.resource_id.gps_binding_ids")
    def _compute_has_trip_gps(self) -> None:
        for batch in self:
            batch.has_trip_gps = (
                bool(batch.vehicle_id.resource_id._gps_device_ids())
                if batch.vehicle_id
                else False
            )

    def _trip_checkpoint(self, event_type, **vals):
        reading = self.env.context.get("trip_gps_reading")
        if reading:
            vals.setdefault("method", "gps")
            vals.setdefault("date", reading["timestamp"])
            vals.setdefault("latitude", reading["latitude"])
            vals.setdefault("longitude", reading["longitude"])
        return super()._trip_checkpoint(event_type, **vals)

    @staticmethod
    def _gps_reading(log) -> dict:
        return {
            "timestamp": log.timestamp,
            "latitude": log.latitude,
            "longitude": log.longitude,
        }

    def _trip_alert(self, vehicle, alert_type, date, **vals):
        Alert = self.env["stock.trip.alert"]
        existing = Alert.search(
            [
                ("alert_type", "=", alert_type),
                ("vehicle_id", "=", vehicle.id),
                ("date", "=", date),
                ("picking_id", "=", vals.get("picking_id", False)),
            ],
            limit=1,
        )
        if existing:
            return existing
        return Alert.create(
            {
                "alert_type": alert_type,
                "vehicle_id": vehicle.id,
                "date": date,
                "batch_id": self.id or False,
                "company_id": (self.company_id or self.env.company).id,
                **vals,
            }
        )

    @api.model
    def _cron_trip_gps_sync(self) -> None:
        vehicles = self.env["resource.asset.vehicle"].search(
            [
                (
                    "resource_id",
                    "in",
                    self.env["resource.gps.binding"]._tracked_resource_ids(),
                )
            ]
        )
        for vehicle in vehicles:
            try:
                with self.env.cr.savepoint():
                    self._trip_gps_sync_vehicle(vehicle)
            except Exception:
                _logger.exception("GPS sync failed for vehicle %s", vehicle.id)

    def action_trip_gps_sync(self) -> None:
        self.check_access("write")
        trips = self.with_privilege(
            "stock_fleet_trace_gps.privilege_trip_gps_read",
            reason="a trip reads its vehicle's track",
        )
        for vehicle in trips.vehicle_id.filtered(
            lambda vehicle: vehicle.resource_id._gps_device_ids()
        ):
            trips._trip_gps_sync_vehicle(vehicle)

    @api.model
    def _trip_gps_sync_vehicle(self, vehicle) -> None:
        warehouses = (
            self.env["stock.warehouse"].search([]).filtered("has_trip_geofence")
        )
        cursor = vehicle.trip_gps_cursor or (fields.Datetime.now() - FIRST_READ_WINDOW)
        logs = self.env["device.data.log.gps"].search(
            [
                *vehicle.resource_id._gps_observation_domain(),
                ("timestamp", ">", cursor),
            ],
            order="timestamp asc, id asc",
        )

        def containing(log):
            return next(
                (
                    wh
                    for wh in warehouses
                    if wh._trip_geofence_contains(log.latitude, log.longitude)
                ),
                self.env["stock.warehouse"],
            )

        inside = vehicle.trip_gps_inside_warehouse_id
        if logs and not vehicle.trip_gps_cursor:
            inside = containing(logs[0])
            logs_to_scan = logs[1:]
        else:
            logs_to_scan = logs
        for log in logs_to_scan:
            now_inside = containing(log)
            if inside and not now_inside:
                self._trip_gps_on_exit(vehicle, log, inside)
            elif now_inside and not inside:
                self._trip_gps_on_entry(vehicle, log, now_inside)
            inside = now_inside
        if logs:
            vehicle.write(
                {
                    "trip_gps_cursor": logs[-1].timestamp,
                    "trip_gps_inside_warehouse_id": inside.id,
                }
            )
        trips = self.search(
            [
                ("vehicle_id", "=", vehicle.id),
                ("date_departure", "!=", False),
                "|",
                ("date_return", "=", False),
                ("date_return", ">=", fields.Datetime.now() - FIRST_READ_WINDOW),
            ]
        )
        for trip in trips:
            trip._trip_gps_review_route()

    def _trip_gps_on_exit(self, vehicle, log, warehouse) -> None:
        reading = self._gps_reading(log)
        trips = self.search(
            [
                ("vehicle_id", "=", vehicle.id),
                ("picking_type_id.warehouse_id", "=", warehouse.id),
                ("trip_state", "in", ("planned", "loaded", "in_transit")),
            ],
            order="date_loaded desc, id desc",
        )
        trip = (
            trips.filtered(lambda t: t.trip_state == "in_transit")
            or trips.filtered(lambda t: t.trip_state == "loaded")
            or trips
        )[:1]
        if trip.trip_state == "in_transit":
            if not trip.trip_gps_exit_date:
                trip.trip_gps_exit_date = log.timestamp
            return
        if not trip or not trip.has_trip_trace:
            if vehicle.trip_delivery_vehicle:
                self._trip_alert(
                    vehicle,
                    "departure_without_trip",
                    log.timestamp,
                    latitude=log.latitude,
                    longitude=log.longitude,
                    note=warehouse.name,
                )
            return
        if trip.trip_state == "planned":
            trip._trip_alert(
                vehicle,
                "departure_not_loaded",
                log.timestamp,
                latitude=log.latitude,
                longitude=log.longitude,
                note=trip.name,
            )
            return
        vals = {"trip_gps_exit_date": log.timestamp}
        odometer = vehicle.resource_id._gps_odometer_at(log.timestamp)
        if odometer:
            vals["odometer_departure"] = odometer
        if log.fuel_level and trip.fuel_unit == "percent":
            vals["fuel_departure"] = log.fuel_level
        trip._trip_gps_write_readings(vehicle, log, vals)
        try:
            with self.env.cr.savepoint():
                trip.with_context(
                    trip_gps_reading=reading,
                    trip_departure_date=min(log.timestamp, fields.Datetime.now()),
                ).action_depart()
        except UserError as error:
            trip._trip_alert(
                vehicle,
                "departure_blocked",
                log.timestamp,
                latitude=log.latitude,
                longitude=log.longitude,
                note=str(error)[:250],
            )

    def _trip_gps_on_entry(self, vehicle, log, warehouse) -> None:
        trip = self.search(
            [
                ("vehicle_id", "=", vehicle.id),
                ("picking_type_id.warehouse_id", "=", warehouse.id),
                ("trip_state", "=", "in_transit"),
            ],
            order="date_departure desc, id desc",
            limit=1,
        )
        if not trip:
            return
        vals = {"trip_gps_entry_date": log.timestamp}
        odometer = vehicle.resource_id._gps_odometer_at(log.timestamp)
        if odometer and not trip.odometer_return:
            vals["odometer_return"] = odometer
        if log.fuel_level and trip.fuel_unit == "percent" and not trip.fuel_return:
            vals["fuel_return"] = log.fuel_level
        trip._trip_gps_write_readings(vehicle, log, vals)
        pending = trip.picking_ids.filtered(
            lambda p: p.state not in ("done", "cancel") and p._requires_trip()
        )
        if (
            pending
            or not trip.odometer_return
            or (trip.has_trip_trace and not trip.fuel_return)
        ):
            trip._trip_alert(
                vehicle,
                "returned_pending",
                log.timestamp,
                latitude=log.latitude,
                longitude=log.longitude,
                note=", ".join(pending.mapped("name")) or trip.name,
            )
            return
        trip._trip_gps_review_route()
        context = {"trip_gps_reading": self._gps_reading(log)}
        if log.timestamp >= trip.date_departure:
            context["trip_return_date"] = min(log.timestamp, fields.Datetime.now())
        trip.with_context(**context).action_return()

    def _trip_gps_write_readings(self, vehicle, log, vals) -> None:
        self.check_singleton()
        try:
            with self.env.cr.savepoint():
                self.write(vals)
        except ValidationError as error:
            stamps = {
                key: value for key, value in vals.items() if key.startswith("trip_gps_")
            }
            self.write(stamps)
            self._trip_alert(
                vehicle,
                "reading_conflict",
                log.timestamp,
                latitude=log.latitude,
                longitude=log.longitude,
                note=str(error)[:250],
            )

    def _trip_gps_window_logs(self):
        self.check_singleton()
        start = self.trip_gps_exit_date or self.date_departure
        end = self.trip_gps_entry_date or self.date_return or fields.Datetime.now()
        return self.env["device.data.log.gps"].search(
            [
                *self.vehicle_id.resource_id._gps_observation_domain(),
                ("timestamp", ">=", start),
                ("timestamp", "<=", end),
            ],
            order="timestamp asc, id asc",
        )

    @staticmethod
    def _dwells(logs, near, min_minutes) -> list:
        runs, current = [], []
        for log in logs:
            if near(log):
                current.append(log)
                continue
            if current:
                runs.append(current)
            current = []
        if current:
            runs.append(current)
        return [
            (run[0], run[-1])
            for run in runs
            if (run[-1].timestamp - run[0].timestamp) >= timedelta(minutes=min_minutes)
        ]

    def _trip_gps_stop_pickings(self):
        self.check_singleton()
        return (
            self.picking_ids
            | self.trip_checkpoint_ids.filtered(
                lambda c: c.event_type == "not_delivered"
            ).picking_id
        )

    def _gps_leg_stops(self):
        self.check_singleton()
        end = self.date_return or fields.Datetime.now()
        visited = (
            self._trip_gps_stop_pickings()
            .filtered(
                lambda p: (
                    p.trip_gps_arrival
                    and p.trip_gps_departure
                    and self.date_departure <= p.trip_gps_arrival <= end
                )
            )
            .sorted(lambda p: (p.trip_gps_arrival, p.id))
        )
        if not visited:
            return super()._gps_leg_stops()
        return self._gps_group_stops(
            [(p, p.trip_gps_arrival, p.trip_gps_departure) for p in visited]
        )

    def _trip_gps_review_route(self) -> None:
        self.check_singleton()
        if not self.vehicle_id.resource_id._gps_device_ids() or not self.date_departure:
            return
        warehouse = self.picking_type_id.warehouse_id
        vehicle = self.vehicle_id
        logs = self._trip_gps_window_logs()
        if not logs:
            return
        stops = self._trip_gps_stop_pickings()
        points = []
        for picking in stops:
            location = picking._trip_location()
            if not location:
                self._trip_alert(
                    vehicle,
                    "customer_without_location",
                    self.date_departure,
                    picking_id=picking.id,
                    note=picking.partner_id.display_name,
                )
                continue
            points.append((picking, location))
            radius = warehouse.trip_stop_radius
            visits = self._dwells(
                logs,
                lambda log, loc=location, r=radius: (
                    haversine_m(loc[0], loc[1], log.latitude, log.longitude) <= r
                ),
                warehouse.trip_stop_min_minutes,
            )
            if visits and not picking.trip_gps_verified:
                first, last = visits[0]
                picking.write(
                    {
                        "trip_gps_arrival": first.timestamp,
                        "trip_gps_departure": last.timestamp,
                        "trip_gps_verified": True,
                        "trip_arrival_date": picking.trip_arrival_date
                        or first.timestamp,
                    }
                )
                self.with_context(
                    trip_gps_reading=self._gps_reading(first)
                )._trip_checkpoint(
                    "arrival",
                    picking_id=picking.id,
                    note=self.env._(
                        "%(minutes)s min at the customer.",
                        minutes=int(
                            (last.timestamp - first.timestamp).total_seconds() // 60
                        ),
                    ),
                )
        self._trip_gps_check_outcomes(logs)
        self._trip_gps_unplanned_stops(logs, points)
        self._trip_gps_driving_and_fuel(logs)
        self._trip_gps_silence(logs)

    def _trip_gps_check_outcomes(self, logs) -> None:
        if not (self.trip_gps_entry_date or self.date_return):
            return
        vehicle = self.vehicle_id
        stops = self._trip_gps_stop_pickings()
        for picking in stops.filtered(
            lambda p: p.trip_delivery_result and not p.trip_gps_verified
        ):
            if not picking._trip_location():
                continue
            self._trip_alert(
                vehicle,
                "outcome_without_visit",
                picking.date_done or logs[-1].timestamp,
                picking_id=picking.id,
                note=picking.trip_delivery_result,
            )

    def _trip_gps_unplanned_stops(self, logs, points) -> None:
        warehouse = self.picking_type_id.warehouse_id
        radius = warehouse.trip_stop_radius

        def unplanned(log):
            if (log.speed or 0.0) > STANDING_SPEED:
                return False
            if warehouse._trip_geofence_contains(log.latitude, log.longitude):
                return False
            return all(
                haversine_m(loc[0], loc[1], log.latitude, log.longitude) > radius
                for _picking, loc in points
            )

        for first, last in self._dwells(
            logs, unplanned, warehouse.trip_unplanned_stop_minutes
        ):
            self._trip_alert(
                self.vehicle_id,
                "unplanned_stop",
                first.timestamp,
                latitude=first.latitude,
                longitude=first.longitude,
                duration_minutes=int(
                    (last.timestamp - first.timestamp).total_seconds() // 60
                ),
            )

    def _trip_gps_driving_and_fuel(self, logs) -> None:
        harsh = logs.filtered(lambda log: log.event_type == HARSH_DRIVING_EVENT)
        if harsh:
            self.trip_harsh_event_count = len(harsh)
        for log in harsh:
            self._trip_alert(
                self.vehicle_id,
                "harsh_driving",
                log.timestamp,
                latitude=log.latitude,
                longitude=log.longitude,
                note=f"{log.speed or 0:.0f} km/h",
            )
        fuel_logged = set(
            self.trip_checkpoint_ids.filtered(lambda c: c.event_type == "fuel").mapped(
                "date"
            )
        )
        for log in logs.filtered(lambda log: log.fuel_refilled > 0):
            if log.timestamp in fuel_logged:
                continue
            self.with_context(trip_gps_reading=self._gps_reading(log))._trip_checkpoint(
                "fuel",
                fuel_level=log.fuel_level,
                quantity=log.fuel_refilled,
                note=self.env._("Refuelling detected by the GPS."),
            )

    def _trip_gps_silence(self, logs) -> None:
        limit = timedelta(
            minutes=self.picking_type_id.warehouse_id.trip_gps_silence_minutes
        )
        end = self.trip_gps_entry_date or self.date_return or fields.Datetime.now()
        previous = self.trip_gps_exit_date or self.date_departure
        for log in [*logs, None]:
            moment = log.timestamp if log else end
            if moment - previous > limit:
                self._trip_alert(
                    self.vehicle_id,
                    "gps_silent",
                    previous,
                    duration_minutes=int((moment - previous).total_seconds() // 60),
                )
            previous = moment
