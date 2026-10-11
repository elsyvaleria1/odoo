import itertools
import logging
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..tools import GPS_DRIFT_THRESHOLD_KM, GPS_MAX_GAP_SECONDS, has_fix, haversine_km

_logger = logging.getLogger(__name__)


class DeviceDataLogGps(models.Model):
    _name = "device.data.log.gps"
    _inherit = ["mixin.device.data.log"]
    _description = "IoT GPS Tracking log"
    _rec_name = "timestamp"

    _fdw_checked_references = ("device_id", "channel_id")
    _fdw_pointer_columns = (("device_device", "log_gps_last_id"),)

    channel_id = fields.Many2one(
        comodel_name="device.channel",
        index="btree_not_null",
        copy=False,
        readonly=True,
        ondelete="restrict",
        help="Channel that admitted this sample. Empty for legacy or non-channel ingestion.",
    )

    @api.depends("device_id", "timestamp")
    @api.depends_context("tz")
    def _compute_display_name(self) -> None:
        for record in self:
            when = (
                fields.Datetime.context_timestamp(record, record.timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if record.timestamp
                else ""
            )
            record.display_name = " · ".join(
                filter(None, [record.device_id.display_name, when])
            )

    @api.constrains("channel_id", "device_id")
    def _check_channel_subject(self) -> None:
        for record in self.filtered("channel_id"):
            if record.channel_id.enrollment_id.device_id != record.device_id:
                raise ValidationError(
                    self.env._(
                        "The GPS sample must retain its channel's admitted device."
                    )
                )

    def write(self, vals):
        if "channel_id" in vals and any(
            record.channel_id.id != vals["channel_id"] for record in self
        ):
            raise UserError(
                self.env._(
                    "A GPS sample cannot be assigned a different admission channel."
                )
            )
        for record in self.filtered("channel_id"):
            if any(
                name in vals and vals[name] != record[name].id
                for name in ("channel_id", "device_id")
            ):
                raise UserError(
                    self.env._("A GPS sample's admitted source cannot be changed.")
                )
        return super().write(vals)

    altitude = fields.Float(help="Altitude in meters above sea level")
    latitude = fields.Float(
        digits=(10, 7),
        required=True,
        help="GPS Latitude coordinate",
    )
    longitude = fields.Float(
        digits=(10, 7),
        required=True,
        help="GPS Longitude coordinate",
    )
    ignition = fields.Boolean(help="Vehicle ignition state")
    movement = fields.Boolean(help="Vehicle is moving")
    speed = fields.Float(help="Speed in kilometers per hour")
    wheel_speed = fields.Float()
    parking_brake_state = fields.Integer()
    central_lock = fields.Integer()
    heading = fields.Float(help="Direction in degrees (0-360)")
    satellites = fields.Integer(help="Number of GPS satellites in view")
    accuracy = fields.Float(help="GPS accuracy in meters")
    gnss_status = fields.Integer()
    gnss_pdop = fields.Float(digits=(16, 2))
    gnss_hdop = fields.Float(digits=(16, 2))
    sleep_mode = fields.Integer()
    hdop = fields.Float(help="Horizontal Dilution of Precision")
    pdop = fields.Float(help="Position Dilution of Precision")
    odometer = fields.Float(help="Odometer reading in kilometers")
    total_odometer = fields.Float(help="Total odometer reading in kilometers")
    real_odometer = fields.Float(
        digits=(16, 2),
        compute="_compute_real_odometer",
        store=True,
        help="Corrected odometer reading based on device configuration",
    )
    odometer_valid = fields.Boolean(
        default=True,
        help="Flag to mark odometer reading as valid. Set to False for erroneous data.",
    )
    fuel_level = fields.Float(help="Fuel level percentage")
    fuel_level_l = fields.Float(digits=(16, 2))
    fuel_consumed = fields.Float(
        help="Fuel consumed in liters (computed from delta if not reported by device)"
    )
    fuel_theft_suspected = fields.Boolean(
        help="The drop that produced fuel_consumed exceeded the device's theft "
        "threshold. Separate from fuel_consumed, which records every drop "
        "above the noise floor, so a suspicious loss is still counted as fuel "
        "that left the tank."
    )
    fuel_refilled = fields.Float(
        help="Fuel added during refueling event (computed from positive delta above threshold)"
    )
    engine_hours = fields.Float(help="Total engine running hours")
    engine_temperature = fields.Float(help="Engine temperature in Celsius")
    engine_speed_rpm = fields.Float(help="Engine revolutions per minute")
    engine_total_hours = fields.Float(digits=(16, 2))
    external_voltage = fields.Float(help="External power supply voltage")
    battery_voltage = fields.Float(help="Vehicle battery voltage")
    battery_current = fields.Float(digits=(16, 3))
    battery_level = fields.Float(
        help="Battery charge level as a percentage (0-100), for devices with an "
        "internal battery (phones, trackers reporting Teltonika AVL 113). "
        "Distinct from battery_voltage."
    )
    gsm_signal = fields.Integer(help="GSM signal strength")
    active_gsm_operator = fields.Integer()
    event_type = fields.Char(help="Type of event that triggered this log")
    event_id = fields.Integer()
    priority = fields.Integer(help="Event priority")
    isf_check_engine_indicator = fields.Integer()
    iccid1 = fields.Char(help="Reported Teltonika AVL 11 SIM identity fragment")
    iccid2 = fields.Char(
        help="Reported Teltonika AVL 14 SIM identity fragment; not IMEI"
    )
    control_state_flags = fields.Char(
        help="This is an hexadecimal flag to check vehicle state"
    )
    ignition_anomaly = fields.Boolean(
        default=False,
        help="Flag indicating suspicious ignition pattern (ON without movement for extended periods)",
    )

    @api.depends("device_id", "odometer", "total_odometer")
    def _compute_real_odometer(self) -> None:
        for log in self:
            device = log.device_id
            config = device.config_id if device else None

            if not config:
                log.real_odometer = 0.0
                continue

            if config.reports_odometer:
                raw_odometer = log.odometer or 0
            else:
                raw_odometer = log.total_odometer or 0

            log.real_odometer = config.real_odometer_from_raw(raw_odometer, device)

    @api.model
    def create_gps_log(self, vals) -> Self:
        if not vals:
            raise ValueError("Cannot create GPS log with empty values")

        required_fields = ["device_id", "latitude", "longitude", "timestamp"]
        missing_fields = [
            f for f in required_fields if f not in vals or vals[f] is None
        ]

        if missing_fields:
            raise ValueError(
                f"Cannot create GPS log: missing required fields {missing_fields}",
            )

        if "source" not in vals:
            vals["source"] = "webhook"

        return self.create(vals)

    _RECOMPUTE_BATCH_SIZE = 20000

    @api.model
    def _schedule_real_odometer_recompute(self, devices) -> None:
        if not devices:
            return
        self.env["device.data.log.gps.report"]._rolling_mark_stale()
        self.sudo().delayed()._job_recompute_real_odometer(devices.ids)

    @api.job(channel="remote_gps_odometer", max_retries=0)
    def _job_recompute_real_odometer(self, device_ids) -> None:
        log_ids = self.sudo().search([("device_id", "in", device_ids)], order="id").ids
        for batch_ids in itertools.batched(
            log_ids, self._RECOMPUTE_BATCH_SIZE, strict=False
        ):
            self.sudo().browse(batch_ids).delayed()._job_recompute_real_odometer_batch()
        _logger.info(
            "real_odometer recompute of %s row(s) of %s device(s) split into "
            "jobs of %s",
            len(log_ids),
            len(device_ids),
            self._RECOMPUTE_BATCH_SIZE,
        )

    @api.job(channel="remote_gps_odometer", max_retries=0)
    def _job_recompute_real_odometer_batch(self) -> None:
        self.modified(["odometer"])
        self.flush_recordset(["real_odometer"])

    @api.autovacuum
    def _gc_gps_data_logs(self):
        self._gc_old_raw_payloads()
        return self._gc_old_data_logs()

    _TRAIL_FIELDS = (
        "device_id",
        "timestamp",
        "latitude",
        "longitude",
        "speed",
        "real_odometer",
        "odometer_valid",
        "fuel_level",
        "fuel_level_l",
        "fuel_refilled",
        "ignition",
        "movement",
    )

    _TRAIL_DRIFT_THRESHOLD_KM = GPS_DRIFT_THRESHOLD_KM

    _TRAIL_MAX_GAP_SECONDS = GPS_MAX_GAP_SECONDS

    @api.model
    def trail_points(
        self, device_ids, date_from, date_to, limit=50000, *, observation_domain=None
    ):
        rows = self.search_read(
            [
                *(observation_domain or []),
                ("device_id", "in", list(device_ids)),
                ("timestamp", ">=", date_from),
                ("timestamp", "<=", date_to),
                ("latitude", "!=", 0),
                ("longitude", "!=", 0),
            ],
            list(self._TRAIL_FIELDS),
            order="timestamp asc, id asc",
            limit=limit,
        )
        for row in rows:
            device = row.get("device_id")
            row["device_id"] = device[0] if isinstance(device, tuple) else device
        return self.env["resource.gps.binding"]._attribute_points(rows)

    @api.model
    def trail_coordinates(self, points) -> tuple:
        coords = []
        timestamps = []
        last = None
        for point in points:
            latitude = point["latitude"]
            longitude = point["longitude"]
            if not has_fix(latitude, longitude) or not point["timestamp"]:
                continue
            coord = (longitude, latitude)
            if coord != last:
                coords.append(coord)
                timestamps.append(int(point["timestamp"].timestamp()))
                last = coord
        return coords, timestamps

    @api.model
    def trail_analytics(self, points, tank_capacity_by_device=None):
        analytics = {
            "duration_hours": 0.0,
            "driving_hours": 0.0,
            "idling_hours": 0.0,
            "parked_hours": 0.0,
            "distance_gps": 0.0,
            "distance_odo": 0.0,
            "odometer_start": 0.0,
            "odometer_end": 0.0,
            "speed_avg": 0.0,
            "speed_max": 0.0,
            "fuel_consumed": 0.0,
            "fuel_start": 0.0,
            "fuel_end": 0.0,
            "stop_count": 0,
        }
        if not points:
            return {}

        tanks = tank_capacity_by_device or {}
        if len(points) >= 2:
            span = points[-1]["timestamp"] - points[0]["timestamp"]
            analytics["duration_hours"] = span.total_seconds() / 3600.0

        speeds = []
        odometers = []
        fuels = []
        refilled = 0.0
        previous = None
        previous_ignition = None

        for point in points:
            speed = point["speed"] or 0.0
            if speed > 0:
                speeds.append(speed)
                analytics["speed_max"] = max(analytics["speed_max"], speed)

            odometer = point["real_odometer"] or 0.0
            if odometer > 0 and point["odometer_valid"]:
                odometers.append(odometer)

            litres = point["fuel_level_l"] if (point["fuel_level_l"] or 0) > 0 else None
            if litres is None and (point["fuel_level"] or 0) > 0:
                tank = tanks.get(point["device_id"]) or 0
                if tank > 0:
                    litres = point["fuel_level"] * tank / 100.0
            if litres is not None:
                fuels.append(litres)
            refilled += point.get("fuel_refilled") or 0.0

            ignition = point["ignition"]
            if previous is not None:
                elapsed = (point["timestamp"] - previous["timestamp"]).total_seconds()
                hours = min(elapsed, self._TRAIL_MAX_GAP_SECONDS) / 3600.0
                moving = bool(point["movement"]) or speed > 0
                if moving and ignition is not False:
                    analytics["driving_hours"] += hours
                elif ignition:
                    analytics["idling_hours"] += hours
                else:
                    analytics["parked_hours"] += hours

                if has_fix(previous["latitude"], previous["longitude"]) and has_fix(
                    point["latitude"], point["longitude"]
                ):
                    distance = self.trail_haversine_km(
                        previous["latitude"],
                        previous["longitude"],
                        point["latitude"],
                        point["longitude"],
                    )
                    if distance >= self._TRAIL_DRIFT_THRESHOLD_KM:
                        analytics["distance_gps"] += distance

            if previous_ignition and not ignition:
                analytics["stop_count"] += 1

            previous = point
            previous_ignition = ignition

        if speeds:
            analytics["speed_avg"] = sum(speeds) / len(speeds)

        if len(odometers) >= 2:
            analytics["odometer_start"] = odometers[0]
            analytics["odometer_end"] = odometers[-1]
            analytics["distance_odo"] = odometers[-1] - odometers[0]

        if fuels:
            analytics["fuel_start"] = fuels[0]
            analytics["fuel_end"] = fuels[-1]
            burned = fuels[0] - fuels[-1] + refilled
            if burned > 0:
                analytics["fuel_consumed"] = burned

        return analytics

    @api.model
    def trail_haversine_km(self, lat1, lon1, lat2, lon2):
        return haversine_km(lat1, lon1, lat2, lon2)
