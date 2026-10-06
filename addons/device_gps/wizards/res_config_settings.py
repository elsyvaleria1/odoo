from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    min_satellites = fields.Integer(
        default=4,
        config_parameter="device_gps.min_required_satellites_count",
        help="Minimum number of satellites required for accurate GPS positioning",
    )
    max_hdop = fields.Float(
        default=5.0,
        config_parameter="device_gps.max_hdop_threshold",
        help="Maximum Horizontal Dilution of Precision allowed (lower is better)",
    )

    min_latitude = fields.Float(
        default=-90.0,
        config_parameter="device_gps.min_allowed_latitude_degrees",
        help="Minimum allowed latitude value (degrees)",
    )
    max_latitude = fields.Float(
        default=90.0,
        config_parameter="device_gps.max_allowed_latitude_degrees",
        help="Maximum allowed latitude value (degrees)",
    )
    min_longitude = fields.Float(
        default=-180.0,
        config_parameter="device_gps.min_allowed_longitude_degrees",
        help="Minimum allowed longitude value (degrees)",
    )
    max_longitude = fields.Float(
        default=180.0,
        config_parameter="device_gps.max_allowed_longitude_degrees",
        help="Maximum allowed longitude value (degrees)",
    )

    max_realistic_speed = fields.Float(
        default=300.0,
        config_parameter="device_gps.max_realistic_speed_kmh",
        help="Maximum reasonable speed for ground vehicles (GPS-based)",
    )
    max_fuel_level_percentage = fields.Float(
        default=100.0,
        config_parameter="device_gps.max_fuel_level_percentage",
        help="Maximum fuel level percentage allowed",
    )
    max_engine_total_hours = fields.Integer(
        default=50000,
        config_parameter="device_gps.max_engine_total_hours",
        help="Maximum reasonable engine hours for validation",
    )
    max_engine_speed_rpm = fields.Integer(
        default=20000,
        config_parameter="device_gps.max_engine_speed_rpm",
        help="Maximum reasonable engine RPM for validation",
    )

    max_time_past_hours = fields.Float(
        default=24.0,
        config_parameter="device_gps.max_time_past_hours",
        help="Maximum allowed time gap for timestamps in the past",
    )
    max_time_future_minutes = fields.Float(
        default=5.0,
        config_parameter="device_gps.max_time_future_minutes",
        help="Maximum allowed time gap for timestamps in the future",
    )

    duplicate_time_window_seconds = fields.Integer(
        default=15,
        config_parameter="device_gps.duplicate_time_window_seconds",
        help="Time window for duplicate point detection",
    )
    duplicate_coordinate_tolerance = fields.Float(
        default=0.00001,
        config_parameter="device_gps.duplicate_coordinate_tolerance",
        help="Coordinate tolerance for duplicate detection (degrees)",
    )

    def execute(self):
        res = super().execute()
        self.env["device.gps.data.validator"].clear_validation_cache()
        return res
