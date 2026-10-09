import logging

from odoo import api, fields, models

from odoo.addons.device.tools.ingest import DeviceIngest, parse_epoch_or_iso

_logger = logging.getLogger(__name__)

_LAT_KEYS = ("latitude", "lat")
_LON_KEYS = ("longitude", "lon", "lng")
_ALT_KEYS = ("altitude", "alt")
_HEADING_KEYS = ("heading", "bearing")
_ACCURACY_KEYS = ("accuracy", "acc")
_BATTERY_KEYS = ("battery_level", "battery", "batt")
_TIMESTAMP_KEYS = ("timestamp", "time")


class DeviceDataLogGps(models.Model):
    _inherit = "device.data.log.gps"

    @api.model
    def create_from_mobile(self, device, points):
        return self.ingest_from_mobile(device, points).created

    @api.model
    def ingest_from_mobile(self, device, points):
        prepared = []
        skipped = []
        for index, point in enumerate(points):
            vals = self._mobile_point_to_vals(device, point)
            if vals is None or any(
                vals.get(field) is None for field in self._MOBILE_REQUIRED_FIELDS
            ):
                skipped.append(index)
                continue
            vals.setdefault("source", "webhook")
            prepared.append(vals)
        skipped = tuple(skipped)
        if not prepared:
            return DeviceIngest(self.browse(), 0, skipped)

        fresh = self._remove_already_stored(device, prepared)
        duplicates = len(prepared) - len(fresh)
        if not fresh:
            return DeviceIngest(self.browse(), duplicates, skipped)

        return DeviceIngest(self.create(fresh), duplicates, skipped)

    _MOBILE_REQUIRED_FIELDS = ("device_id", "latitude", "longitude", "timestamp")

    @api.model
    def _remove_already_stored(self, device, prepared):
        # The key holds the stamp exactly, so only rows at the batch's own
        # stamps can match: a backlog spanning days read every row in between.
        stamps = sorted({vals["timestamp"] for vals in prepared})
        existing = self.search_read(
            [("device_id", "=", device.id), ("timestamp", "in", stamps)],
            ["timestamp", "latitude", "longitude"],
        )
        seen = {
            self._mobile_fix_key(row["timestamp"], row["latitude"], row["longitude"])
            for row in existing
        }
        fresh = []
        for vals in prepared:
            key = self._mobile_fix_key(
                vals["timestamp"], vals["latitude"], vals["longitude"]
            )
            if key in seen:
                continue
            seen.add(key)
            fresh.append(vals)
        return fresh

    @staticmethod
    def _mobile_fix_key(timestamp, latitude, longitude) -> tuple:
        return (timestamp, round(latitude or 0.0, 7), round(longitude or 0.0, 7))

    @api.model
    def _mobile_point_to_vals(self, device, point):
        if not isinstance(point, dict):
            return None
        latitude = self._pick_coordinate(point, _LAT_KEYS, 90.0)
        longitude = self._pick_coordinate(point, _LON_KEYS, 180.0)
        if latitude is None or longitude is None:
            return None
        vals = {
            "device_id": device.id,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": self._mobile_timestamp(point),
            "source": "webhook",
        }
        for target, keys in (
            ("altitude", _ALT_KEYS),
            ("heading", _HEADING_KEYS),
            ("accuracy", _ACCURACY_KEYS),
        ):
            value = self._pick_float(point, keys)
            if value is not None:
                vals[target] = value
        speed = self._mobile_speed_kmh(point)
        if speed is not None:
            vals["speed"] = speed
            vals["movement"] = speed >= self._mobile_motion_threshold(device)
        satellites = self._pick_int(point, ("satellites", "sats"))
        if satellites is not None:
            vals["satellites"] = satellites
        battery = self._pick_float(point, _BATTERY_KEYS)
        if battery is not None and 0 <= battery <= 100:
            vals["battery_level"] = battery
        return vals

    _MPS_TO_KMH = 3.6

    _SPEED_UNITS = {"mps": _MPS_TO_KMH, "m/s": _MPS_TO_KMH, "kmh": 1.0, "km/h": 1.0}

    @api.model
    def _mobile_speed_kmh(self, point):
        speed = self._pick_float(point, ("speed",))
        if speed is None:
            return None
        unit = str(point.get("speed_unit") or "mps").strip().lower()
        factor = self._SPEED_UNITS.get(unit)
        if factor is None:
            _logger.warning("Unknown speed_unit %r from phone fix; assuming m/s", unit)
            factor = self._MPS_TO_KMH
        return speed * factor

    @api.model
    def _mobile_motion_threshold(self, device):
        config = device.config_id
        threshold = getattr(config, "motion_threshold_speed", 0.0) or 0.0
        return threshold or 1.0

    @api.model
    def _pick_coordinate(self, point, keys, bound):
        value = self._pick_float(point, keys)
        if value is None or not -bound <= value <= bound:
            return None
        return value

    @api.model
    def _pick_float(self, point, keys) -> float | None:
        for key in keys:
            if key not in point or point[key] is None:
                continue
            try:
                return float(point[key])
            except TypeError, ValueError:
                continue
        return None

    @api.model
    def _pick_int(self, point, keys):
        value = self._pick_float(point, keys)
        return int(value) if value is not None else None

    @api.model
    def _mobile_timestamp(self, point):
        for key in _TIMESTAMP_KEYS:
            parsed = parse_epoch_or_iso(point.get(key))
            if parsed is not None:
                return parsed
        return fields.Datetime.now()
