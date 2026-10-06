import logging
from datetime import datetime, timedelta
from typing import Any

from odoo import api, fields, models, tools

from ..tools import has_fix, haversine_m

_logger = logging.getLogger(__name__)


class GpsValidationService(models.AbstractModel):
    _name = "device.gps.data.validator"
    _description = "GPS Data Validation Service"

    @api.model
    def _check_gps_quality(
        self,
        vals: dict[str, Any],
        device: Any,
        processing_stats: dict[str, datetime | float | int],
        recent_points: Any = None,
    ) -> tuple[bool, str]:
        errors = []
        warnings = []

        window = self._threshold("duplicate_time_window")
        if recent_points is None:
            recent_points = self.env["device.data.log.gps"].get_log_last_ids(
                device,
                time_window_seconds=window,
            )
        else:
            cutoff = fields.Datetime.now() - timedelta(seconds=window)
            recent_points = recent_points.filtered(
                lambda point: point.timestamp and point.timestamp >= cutoff
            )

        validation_rules = [
            (
                "timestamp_quality",
                self._check_timestamp,
                "critical",
            ),
            (
                "coordinate_quality",
                self._check_coordinates,
                "critical",
            ),
            (
                "record_duplication",
                self._check_record_duplication,
                "critical",
            ),
            (
                "comprehensive_parameters",
                self._check_comprehensive_parameters,
                "warning",
            ),
        ]

        for rule_name, validator_func, severity in validation_rules:
            try:
                is_valid, message = validator_func(vals, recent_points)

                if is_valid:
                    processing_stats["quality_checks_passed"] += 1
                else:
                    processing_stats["quality_checks_failed"] += 1
                    if severity == "critical":
                        errors.append(f"{rule_name}: {message}")
                    elif severity == "warning":
                        warnings.append(f"{rule_name}: {message}")

            except Exception:
                processing_stats["quality_checks_failed"] += 1
                _logger.exception(
                    "Validation exception in rule '%s' for device %s",
                    rule_name,
                    device.id if device else "unknown",
                )
                errors.append(f"{rule_name}: Validation failed due to system error")

        if errors:
            error_summary = f"Validation failed for device {device.id if device else 'unknown'}: {'; '.join(errors)}"
            _logger.debug("GPS validation failed: %s", error_summary)
            return False, error_summary

        if warnings:
            warning_summary = f"GPS validation warnings for device {device.id if device else 'unknown'}: {'; '.join(warnings)}"
            _logger.debug(warning_summary)

        passed_checks = processing_stats.get("quality_checks_passed", 0)
        total_checks = passed_checks + processing_stats.get("quality_checks_failed", 0)
        success_message = (
            f"Validation successful: {passed_checks}/{total_checks} checks passed"
        )

        return True, success_message

    @api.model
    def _check_comprehensive_parameters(
        self,
        vals: dict[str, Any],
        recent_points: Any | None = None,
    ) -> tuple[bool, str]:
        has_errors = False
        errors = []

        satellites = vals.get("satellites", 0.0)
        min_required_satellites_count = self._threshold("min_satellites")
        is_valid, msg = self._check_range(
            "GPS accuracy (count)",
            min_required_satellites_count,
            1000.0,
            satellites,
            "",
        )
        if not is_valid and satellites > 0.0:
            has_errors = True
            errors.append(msg)

        gnss_hdop = vals.get("gnss_hdop", 0.0)
        max_hdop_threshold = self._threshold("max_hdop")
        is_valid, msg = self._check_range(
            "GNSS hdop",
            0.0,
            max_hdop_threshold,
            gnss_hdop,
            "",
        )
        if not is_valid and gnss_hdop > 0.0:
            has_errors = True
            errors.append(msg)

        fuel_level = vals.get("fuel_level", 0.0)
        max_fuel_level_percentage = self._threshold("max_fuel_level")
        is_valid, msg = self._check_range(
            "fuel level",
            0.0,
            max_fuel_level_percentage,
            fuel_level,
            "%",
        )
        if not is_valid and fuel_level > 0.0:
            has_errors = True
            errors.append(msg)

        engine_total_hours = vals.get("engine_total_hours", 0.0)
        max_engine_total_hours = self._threshold("max_engine_hours")
        is_valid, msg = self._check_range(
            "engine hours",
            0.0,
            max_engine_total_hours,
            engine_total_hours,
            "hours",
        )
        if not is_valid and engine_total_hours > 0.0:
            has_errors = True
            errors.append(msg)

        speed = vals.get("speed", 0.0)
        max_realistic_speed_kmh = self._threshold("max_speed")
        is_valid, msg = self._check_range(
            "speed",
            0.0,
            max_realistic_speed_kmh,
            speed,
            "km/h",
        )
        if not is_valid and speed > 0.0:
            has_errors = True
            errors.append(msg)

        engine_speed_rpm = vals.get("engine_speed_rpm", 0.0)
        max_engine_speed_rpm = self._threshold("max_engine_rpm")
        is_valid, msg = self._check_range(
            "engine speed rpm",
            0.0,
            max_engine_speed_rpm,
            engine_speed_rpm,
            "rpm",
        )
        if not is_valid and engine_speed_rpm > 0.0:
            has_errors = True
            errors.append(msg)

        if has_errors:
            return False, f"Comprehensive parameter violations: {'; '.join(errors)}"
        return True, "All comprehensive parameters valid"

    @api.model
    def _check_coordinates(
        self,
        vals: dict[str, Any],
        recent_points: Any | None = None,
    ) -> tuple[bool, str]:
        lat = vals.get("latitude")
        lng = vals.get("longitude")

        if lat is None or lng is None:
            return (
                False,
                "No coordinates to validate",
            )
        if not has_fix(lat, lng):
            return (
                False,
                "Invalid coordinates (0.0, 0.0) - GPS signal not acquired",
            )

        min_latitude = self._threshold("min_latitude")
        max_latitude = self._threshold("max_latitude")
        is_valid, msg = self._check_range(
            "latitude",
            min_latitude,
            max_latitude,
            lat,
            "°",
        )

        if not is_valid:
            return False, msg

        min_longitude = self._threshold("min_longitude")
        max_longitude = self._threshold("max_longitude")
        is_valid, msg = self._check_range(
            "longitude",
            min_longitude,
            max_longitude,
            lng,
            "°",
        )
        if not is_valid:
            return False, msg

        return True, f"Coordinates valid: ({lat:.6f}, {lng:.6f})"

    @api.model
    def _check_prerequisites(
        self,
        payload: dict[str, Any],
        device: Any = None,
        channel: Any = None,
    ) -> tuple[bool, str, Any]:
        devices = self.env["device.device"]
        key = devices._normalize_tracker_key(payload.get("14"))
        if key is None:
            return False, "Missing or invalid GPS receiver key", device
        if channel:
            if (
                channel.purpose != "telemetry"
                or not channel.active
                or channel.enrollment_id.state != "active"
                or channel.enrollment_id.device_id != device
                or channel.external_identifier != key
            ):
                return False, "GPS payload does not match admitted channel", device
            if not device or not device.active:
                return False, "GPS device is inactive", device
            return True, "Prerequisites valid", device
        if device is None:
            device = devices._get_tracker_by_receiver_key(key)
        if not device:
            return False, "GPS receiver not found or ambiguous", device
        if not device.active or device.gps_receiver_key != key:
            return False, "GPS receiver key does not match admitted subject", device

        return True, "Prerequisites valid", device

    @api.model
    def _check_range(
        self,
        param_name: str,
        min_val: float,
        max_val: float,
        value: float,
        unit: str = "",
    ) -> tuple | None:
        if value is None or value == 0:
            return False, f"No {param_name} to validate"

        if not min_val <= value <= max_val:
            return (
                False,
                f"Invalid {param_name}: {value} {unit} (range: {min_val}-{max_val} {unit})",
            )

        return True, f"{param_name} valid"

    @api.model
    def _check_record_duplication(
        self,
        vals: dict[str, Any],
        recent_points: Any,
    ) -> tuple[bool, str]:
        if not recent_points or len(recent_points) == 0:
            return True, "No recent points (first report)"

        timestamp = vals.get("timestamp")
        lat = vals.get("latitude")
        lon = vals.get("longitude")
        if timestamp is None or lat is None or lon is None:
            return True, "Missing required fields for duplicate check"
        duplicate_time_window_seconds = self._threshold("duplicate_time_window")
        duplicate_coordinate_tolerance = self._threshold("duplicate_tolerance")
        latest_point = recent_points[0]
        time_diff = abs((timestamp - latest_point.timestamp).total_seconds())
        if time_diff > duplicate_time_window_seconds:
            return True, "No points within time window"

        lat_min = lat - duplicate_coordinate_tolerance
        lat_max = lat + duplicate_coordinate_tolerance
        lon_min = lon - duplicate_coordinate_tolerance
        lon_max = lon + duplicate_coordinate_tolerance
        for point in recent_points:
            time_diff = abs((timestamp - point.timestamp).total_seconds())
            if time_diff > duplicate_time_window_seconds:
                break

            if not (
                lat_min <= point.latitude <= lat_max
                and lon_min <= point.longitude <= lon_max
            ):
                continue

            if (
                abs(point.latitude - lat) <= duplicate_coordinate_tolerance
                and abs(point.longitude - lon) <= duplicate_coordinate_tolerance
            ):
                return (
                    False,
                    (
                        f"Duplicate point detected: {time_diff:.1f}s ago, "
                        f"distance: {self._haversine_distance(lat, lon, point.latitude, point.longitude):.2f}m"
                    ),
                )
        return True, "No duplicate found"

    @api.model
    def _check_timestamp(
        self,
        vals: dict[str, Any],
        recent_points: Any | None = None,
    ) -> tuple[bool, str]:
        timestamp = vals.get("timestamp")

        if not timestamp:
            return False, "Missing timestamp in GPS data"

        if not isinstance(timestamp, datetime):
            return (
                False,
                f"Invalid timestamp type: expected datetime, got {type(timestamp).__name__}",
            )

        now = fields.Datetime.now()
        time_diff = (timestamp - now).total_seconds()

        max_future_minutes = self._threshold("max_future_minutes")
        max_future_seconds = max_future_minutes * 60
        if time_diff > max_future_seconds:
            return (
                False,
                f"Timestamp too far in future: {time_diff / 60:.1f} minutes ahead",
            )

        max_past_hours = self._threshold("max_past_hours")
        max_past_seconds = max_past_hours * 3600
        if time_diff < -max_past_seconds:
            return (
                False,
                f"Timestamp too old: {abs(time_diff / 3600):.1f} hours ago (maximum: {max_past_hours} hours)",
            )

        return True, "Timestamp quality valid"

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        return haversine_m(lat1, lon1, lat2, lon2)

    _THRESHOLDS = {
        "min_satellites": ("device_gps.min_required_satellites_count", "4", int),
        "max_hdop": ("device_gps.max_hdop_threshold", "5.0", float),
        "min_latitude": ("device_gps.min_allowed_latitude_degrees", "-90.0", float),
        "max_latitude": ("device_gps.max_allowed_latitude_degrees", "90.0", float),
        "min_longitude": ("device_gps.min_allowed_longitude_degrees", "-180.0", float),
        "max_longitude": ("device_gps.max_allowed_longitude_degrees", "180.0", float),
        "max_speed": ("device_gps.max_realistic_speed_kmh", "300.0", float),
        "max_fuel_level": ("device_gps.max_fuel_level_percentage", "100.0", float),
        "max_engine_hours": ("device_gps.max_engine_total_hours", "50000", float),
        "max_engine_rpm": ("device_gps.max_engine_speed_rpm", "20000", float),
        "max_past_hours": ("device_gps.max_time_past_hours", "24", int),
        "max_future_minutes": ("device_gps.max_time_future_minutes", "5", int),
        "duplicate_time_window": (
            "device_gps.duplicate_time_window_seconds",
            "15",
            int,
        ),
        "duplicate_tolerance": (
            "device_gps.duplicate_coordinate_tolerance",
            "0.00001",
            float,
        ),
    }

    @tools.ormcache("name")
    def _threshold(self, name):
        key, default, cast = self._THRESHOLDS[name]
        raw = self.env.registry.settings.get(self.env, key, default=default)
        return cast(float(raw)) if cast is int else cast(raw)

    @api.model
    def clear_validation_cache(self) -> None:
        self.env.registry.clear_cache()
