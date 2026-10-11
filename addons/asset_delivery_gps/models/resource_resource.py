import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TRIP_READING_MAX_AGE_PARAM = "asset_delivery_gps.trip_reading_max_age_minutes"
DEFAULT_TRIP_READING_MAX_AGE_MINUTES = 120


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    def _get_last_gps_log(self, no_device_message: str):
        self.check_singleton()
        if not self.gps_device_id:
            raise UserError(no_device_message)

        last_log = self.gps_device_id.log_gps_last_id
        if not last_log:
            raise UserError(
                self.env._(
                    "No GPS data available for vehicle %s."
                    " Waiting for GPS device to send data.",
                    self.name,
                )
            )
        if self._is_gps_log_stale(last_log):
            raise UserError(
                self.env._(
                    "The last GPS reading for vehicle %(vehicle)s is from"
                    " %(timestamp)s, older than the %(days)s day(s) considered"
                    " current. Please enter the value manually.",
                    vehicle=self.name,
                    timestamp=last_log.timestamp,
                    days=self._gps_odometer_lookback_days(),
                )
            )

        return last_log

    def _is_gps_log_stale(self, gps_log) -> bool:
        if not gps_log.timestamp:
            return True
        cutoff = fields.Datetime.now() - timedelta(
            days=self._gps_odometer_lookback_days()
        )
        return gps_log.timestamp < cutoff

    @api.model
    def _trip_reading_max_age(self) -> timedelta:
        raw = self.env.registry.settings.get(
            self.env, TRIP_READING_MAX_AGE_PARAM, DEFAULT_TRIP_READING_MAX_AGE_MINUTES
        )
        try:
            minutes = int(raw)
        except TypeError, ValueError:
            minutes = 0
        if minutes <= 0:
            _logger.warning(
                "%s is %r, which is not a positive number of minutes; using %d.",
                TRIP_READING_MAX_AGE_PARAM,
                raw,
                DEFAULT_TRIP_READING_MAX_AGE_MINUTES,
            )
            minutes = DEFAULT_TRIP_READING_MAX_AGE_MINUTES
        return timedelta(minutes=minutes)

    def get_current_odometer(self) -> float:
        self.check_singleton()
        if not self.gps_device_id:
            raise UserError(
                self.env._(
                    "No GPS device assigned to vehicle %s."
                    " Please assign a GPS device or enter odometer manually.",
                    self.name,
                )
            )
        max_age = self._trip_reading_max_age()
        reading = self._gps_odometer_reading(before=max_age)
        if not reading:
            raise UserError(
                self.env._(
                    "No valid GPS odometer reading for vehicle %(vehicle)s in the"
                    " last %(minutes)s minutes. Please enter the odometer manually.",
                    vehicle=self.name,
                    minutes=int(max_age.total_seconds() // 60),
                )
            )
        return reading.value

    def get_current_fuel_percentage(self) -> float:
        log = self._get_last_gps_log(
            self.env._(
                "No GPS device assigned to vehicle %s."
                " Please assign a GPS device or enter fuel level manually.",
                self.name,
            )
        )
        return log.fuel_level or 0.0
