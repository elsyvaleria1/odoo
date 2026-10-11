import logging
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GpsDataProcessor(models.AbstractModel):
    _name = "device.gps.data.processor"
    _description = "GPS Data Processing Orchestrator"

    MAX_PLAUSIBLE_SPEED_KMH = 150.0
    ODOMETER_NOISE_TOLERANCE_KM = 1.0
    MAX_PLAUSIBLE_ODOMETER_KM = 2_000_000.0

    TELTONIKA_FIELD_MAPPING: ClassVar[dict[str, str]] = {
        "alt": "altitude",
        "ang": "heading",
        "evt": "event_type",
        "latlng": "latitude_longitude",
        "pr": "priority",
        "sat": "satellites",
        "sp": "speed",
        "ts": "timestamp",
        "11": "iccid1",
        "14": "iccid2",
        "16": "total_odometer",
        "21": "gsm_signal",
        "66": "external_voltage",
        "67": "battery_voltage",
        "68": "battery_current",
        "69": "gnss_status",
        "81": "wheel_speed",
        "84": "fuel_level_l",
        "85": "engine_speed_rpm",
        "87": "odometer",
        "89": "fuel_level",
        "102": "engine_total_hours",
        "113": "battery_level",
        "115": "engine_temperature",
        "123": "control_state_flags",
        "181": "gnss_pdop",
        "182": "gnss_hdop",
        "200": "sleep_mode",
        "239": "ignition",
        "240": "movement",
        "241": "active_gsm_operator",
        "653": "parking_brake_state",
        "662": "central_lock",
        "953": "isf_check_engine_indicator",
    }

    @api.model
    def get_field_mapping(
        self,
        device_type: str = "teltonika",
    ) -> dict[str, str]:
        mappings = {
            "teltonika": self.TELTONIKA_FIELD_MAPPING,
            "generic": self.TELTONIKA_FIELD_MAPPING,
        }
        if device_type not in mappings:
            raise UserError(
                self.env._(
                    "GPS protocol %(protocol)s has no field mapping. Implemented "
                    "protocols: %(known)s.",
                    protocol=device_type,
                    known=", ".join(sorted(mappings)),
                )
            )
        return mappings[device_type]

    @api.model
    def _get_payload(
        self,
        json_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            state = json_data.get("state", {})

            if not isinstance(state, dict):
                _logger.warning("Invalid 'state' structure in payload")
                return None

            reported = state.get("reported", {})

            if not isinstance(reported, dict):
                _logger.warning("Invalid 'reported' structure in payload")
                return None

            if not reported:
                _logger.warning("Empty 'reported'")

            return reported

        except Exception:
            _logger.exception("Failed to extract payload")
            return None

    @api.model
    def _process_gps_data(
        self,
        payload: dict[str, Any],
        processing_stats: dict[str, Any],
        device: Any = None,
        channel: Any = None,
    ) -> tuple[bool, str, Any, dict[str, Any]]:
        validator = self.env["device.gps.data.validator"]

        is_valid, msg, device = validator._check_prerequisites(
            payload, device=device, channel=channel
        )
        if not is_valid:
            processing_stats["quality_checks_failed"] += 1
            return False, msg, None, {}

        processing_stats["quality_checks_passed"] += 1

        history = self._recent_history(device)

        vals = self._prepare_log_vals(device, payload, history=history)
        if channel:
            vals["channel_id"] = channel.id

        if not vals:
            processing_stats["quality_checks_failed"] += 1
            return (
                False,
                "Failed to prepare GPS log values: empty result",
                device,
                {},
            )

        lat = vals.get("latitude")
        lng = vals.get("longitude")
        if lat is None or lng is None:
            processing_stats["quality_checks_failed"] += 1
            return (
                False,
                f"Failed to prepare GPS coordinates: lat={lat}, lng={lng}",
                device,
                vals,
            )

        is_valid, message = validator._check_gps_quality(
            vals,
            device,
            processing_stats,
            recent_points=history,
        )

        if not is_valid:
            return False, message, device, vals

        return True, message, device, vals

    @api.model
    def _prepare_log_vals(
        self,
        device: Any,
        payload: dict[str, Any],
        field_mapping: dict[str, str] | None = None,
        history: Any = None,
    ) -> dict[str, Any]:
        device_protocol = device.config_id.gps_protocol or "teltonika"
        fields_mapped = field_mapping or self.get_field_mapping(device_protocol)
        logs_model = self.env["device.data.log.gps"]
        available_fields = set(logs_model._fields.keys())
        composite_fields = {"latitude_longitude"}
        log_vals = {"device_id": device.id}

        for iot_field, model_field in fields_mapped.items():
            if iot_field not in payload:
                continue

            if (
                model_field not in composite_fields
                and model_field not in available_fields
            ):
                continue

            value = payload[iot_field]
            if value is not None:
                self._process_field_value(
                    model_field,
                    value,
                    log_vals,
                    device_protocol,
                    device,
                )

        self._compute_accuracy_from_hdop(log_vals)

        if history is None:
            history = self._recent_history(device)

        self._compute_fuel_delta(log_vals, device, history)

        self._add_ignition_anomaly(log_vals, device, history)

        self._check_odometer(log_vals, device, history)

        return log_vals

    @api.model
    def _recent_history(self, device, limit=15):
        logs = self.env["device.data.log.gps"]
        if not device:
            return logs
        return logs.search(
            [("device_id", "=", device.id)],
            order="timestamp desc, id desc",
            limit=limit,
        )

    @api.model
    def _compute_accuracy_from_hdop(self, log_vals: dict[str, Any]) -> None:
        if log_vals.get("accuracy"):
            return

        hdop = log_vals.get("gnss_hdop") or log_vals.get("hdop")
        if hdop and hdop > 0:
            gps_base_error = 4.0
            log_vals["accuracy"] = round(hdop * gps_base_error, 2)

    @api.model
    def _process_field_value(
        self,
        field_name: str,
        value: Any,
        log_vals: dict[str, Any],
        device_type: str = "teltonika",
        device: Any = None,
    ) -> None:
        try:
            processor_method_name = f"_process_{field_name}"
            processor_method = getattr(self, processor_method_name, None)

            if processor_method and callable(processor_method):
                result = processor_method(
                    value, device_type=device_type, device=device
                )

                if field_name == "latitude_longitude" and isinstance(result, tuple):
                    lat, lng = result
                    if lat is not None and lng is not None:
                        log_vals["latitude"] = lat
                        log_vals["longitude"] = lng
                elif result is not None:
                    log_vals[field_name] = result
            else:
                log_vals[field_name] = value

        except Exception:
            _logger.warning(
                "Failed to process field '%s' with value %r — skipping",
                field_name,
                value,
                exc_info=True,
            )

    @api.model
    def _process_latitude_longitude(
        self,
        value: str,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> tuple[float | None, float | None]:
        try:
            if device_type == "teltonika":
                if not value or "," not in value:
                    return None, None

                lat_str, lng_str = value.split(",", 1)
                lat = float(lat_str.strip())
                lng = float(lng_str.strip())

                return lat, lng

            if not value or "," not in value:
                return None, None

            lat_str, lng_str = value.split(",", 1)
            return float(lat_str.strip()), float(lng_str.strip())

        except AttributeError, ValueError, TypeError:
            return None, None

    @api.model
    def _process_timestamp(
        self,
        value: int,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> datetime | None:
        try:
            if device_type == "teltonika":
                dt = datetime.fromtimestamp(value / 1000, tz=UTC)
                return dt.replace(tzinfo=None)

            dt = datetime.fromtimestamp(value, tz=UTC)
            return dt.replace(tzinfo=None)

        except TypeError, ValueError, OSError, OverflowError:
            return None

    @api.model
    def _process_odometer(
        self,
        value: float,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> float | None:
        try:
            odometer_km = float(value)

            if device_type == "teltonika":
                odometer_km /= 1000.0

            if odometer_km < 0:
                return None

            return odometer_km

        except TypeError, ValueError:
            return None

    @api.model
    def _process_engine_temperature(
        self,
        value: float,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> float | None:
        try:
            if device_type == "teltonika":
                return float(value) / 10.0
            return float(value)
        except TypeError, ValueError:
            return None

    @api.model
    def _parse_dilution_of_precision(
        self, value: float, device_type: str
    ) -> float | None:
        try:
            dop = float(value)
        except TypeError, ValueError:
            return None
        if dop < 0:
            return None
        if device_type == "teltonika":
            dop /= 10.0
        return dop

    @api.model
    def _process_gnss_hdop(
        self,
        value: float,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> float | None:
        return self._parse_dilution_of_precision(value, device_type)

    @api.model
    def _process_gnss_pdop(
        self,
        value: float,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> float | None:
        return self._parse_dilution_of_precision(value, device_type)

    @api.model
    def _process_fuel_level_l(
        self,
        value: float,
        device_type: str = "teltonika",
        device: Any = None,
    ) -> float | None:
        try:
            fuel_value = float(value)
            if fuel_value < 0:
                return None

            fuel_unit = "deciliters"
            if device and device.config_id:
                fuel_unit = device.config_id.fuel_level_l_unit or "deciliters"

            if fuel_unit == "deciliters":
                return fuel_value / 10.0
            if fuel_unit == "centiliters":
                return fuel_value / 100.0
            return fuel_value

        except TypeError, ValueError:
            return None

    @api.model
    def _compute_fuel_delta(
        self,
        log_vals: dict[str, Any],
        device: Any,
        history: Any = None,
    ) -> None:
        if log_vals.get("fuel_consumed"):
            return

        if history is None:
            history = self._recent_history(device)
        prev_log = history[:1]
        if not prev_log:
            return

        current_fuel = log_vals.get("fuel_level_l") or None
        prev_fuel = prev_log.fuel_level_l or None

        if current_fuel is None or prev_fuel is None:
            tank_capacity = device.fuel_tank_capacity if device else 0
            current_pct = log_vals.get("fuel_level")
            prev_pct = prev_log.fuel_level
            if not (tank_capacity and current_pct and prev_pct):
                return
            current_fuel = current_pct * tank_capacity / 100.0
            prev_fuel = prev_pct * tank_capacity / 100.0

        delta = prev_fuel - current_fuel

        refill_threshold = device.fuel_refill_threshold if device else 5.0
        consumption_threshold = device.fuel_consumption_threshold if device else 0.5
        theft_threshold = device.fuel_theft_threshold if device else 10.0

        if delta < -refill_threshold:
            current_ts = log_vals.get("timestamp")
            if current_ts and prev_log.timestamp:
                time_diff = (current_ts - prev_log.timestamp).total_seconds()
                if time_diff < 300 and prev_log.fuel_refilled:
                    return

            log_vals["fuel_refilled"] = abs(delta)

        elif delta >= consumption_threshold:
            log_vals["fuel_consumed"] = delta
            if delta > theft_threshold:
                log_vals["fuel_theft_suspected"] = True

    @api.model
    def _add_ignition_anomaly(
        self,
        log_vals: dict[str, Any],
        device: Any,
        history: Any = None,
    ) -> None:
        ignition = log_vals.get("ignition")
        movement = log_vals.get("movement", False)
        speed = log_vals.get("speed", 0) or 0

        if not ignition or movement or speed > 0:
            return

        if not device:
            return

        if history is None:
            history = self._recent_history(device)

        cutoff = fields.Datetime.now() - timedelta(hours=24)
        window = [log for log in history if log.timestamp and log.timestamp >= cutoff]
        if len(window) >= 10 and all(
            log.ignition and not log.movement and (log.speed or 0) == 0
            for log in window[:10]
        ):
            log_vals["ignition_anomaly"] = True

    @api.model
    def _check_odometer(
        self,
        log_vals: dict[str, Any],
        device: Any,
        history: Any = None,
    ) -> None:
        config = device.config_id if device else None
        if not config:
            return

        raw = (
            log_vals.get("odometer")
            if config.reports_odometer
            else log_vals.get("total_odometer")
        )
        if not raw:
            return
        candidate = config.real_odometer_from_raw(raw, device)

        if candidate > self.MAX_PLAUSIBLE_ODOMETER_KM:
            log_vals["odometer_valid"] = False
            return

        if history is None:
            history = self._recent_history(device)
        previous = next(
            (log for log in history if log.odometer_valid and log.real_odometer > 0),
            None,
        )
        if previous is None:
            previous = self.env["device.data.log.gps"].search(
                [
                    ("device_id", "=", device.id),
                    ("odometer_valid", "=", True),
                    ("real_odometer", ">", 0),
                ],
                order="timestamp desc, id desc",
                limit=1,
            )
        if not previous:
            return
        prev_real = previous.real_odometer

        if candidate <= 0:
            log_vals["odometer_valid"] = False
            return

        if candidate < prev_real - self.ODOMETER_NOISE_TOLERANCE_KM:
            log_vals["odometer_valid"] = False
            return

        current_ts = log_vals.get("timestamp")
        if current_ts and previous.timestamp:
            elapsed_h = (current_ts - previous.timestamp).total_seconds() / 3600
            if elapsed_h > 0:
                implied_speed = (candidate - prev_real) / elapsed_h
                if implied_speed > self.MAX_PLAUSIBLE_SPEED_KMH:
                    log_vals["odometer_valid"] = False
