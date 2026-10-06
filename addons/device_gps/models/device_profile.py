from odoo import api, exceptions, fields, models, tools


class DeviceConfig(models.Model):
    _inherit = "device.profile"

    gps_tracking_enabled = fields.Boolean(
        string="GPS Tracking Enabled by Default",
        default=True,
        help="Enable GPS tracking by default for devices using this config. Can be overridden at device level.",
    )
    gps_protocol = fields.Selection(
        selection=[
            ("teltonika", "Teltonika"),
            ("queclink", "Queclink"),
            ("concox", "Concox"),
            ("meitrack", "Meitrack"),
            ("generic", "Generic GPS"),
        ],
        string="GPS Device Protocol",
        default="generic",
        help="GPS device-specific protocol (Teltonika, Queclink, etc.). "
        "This works alongside the base communication protocol (MQTT, HTTP, etc.)",
    )
    stationary_interval = fields.Integer(
        string="Stationary Interval (seconds)",
        default=300,
        help="Update interval when device is stationary (saves battery/data)",
    )
    motion_threshold_speed = fields.Float(
        string="Motion Threshold Speed (km/h)",
        default=5.0,
        help="Minimum speed to consider device as moving",
    )
    motion_threshold_distance = fields.Float(
        string="Motion Threshold Distance (m)",
        default=50.0,
        help="Minimum distance to consider device as moving",
    )
    speed_limit_warning = fields.Float(
        string="Speed Warning (km/h)",
        default=80.0,
        help="Level 1: Minor speeding threshold. Triggers warning status.",
    )
    speed_limit_alert = fields.Float(
        string="Speed Alert (km/h)",
        default=100.0,
        help="Level 2: Moderate speeding threshold. Requires attention.",
    )
    speed_limit_critical = fields.Float(
        string="Speed Critical (km/h)",
        default=120.0,
        help="Level 3: Severe speeding threshold. Safety concern.",
    )
    idle_threshold = fields.Integer(
        string="Idle Threshold (minutes)",
        default=30,
        help="Time before idle alert is triggered",
    )
    battery_threshold = fields.Float(
        string="Battery Threshold (%)",
        default=20.0,
        help="Battery level threshold for alerts",
    )
    alert_overspeeding = fields.Boolean(
        string="Enable Overspeeding Alert",
        help="Alert when device exceeds speed limit",
    )
    alert_idle = fields.Boolean(
        string="Enable Idle Alert",
        help="Alert when device is idle for too long",
    )
    alert_battery = fields.Boolean(
        string="Enable Battery Alert",
        help="Alert on low battery",
    )

    reports_odometer = fields.Boolean(
        default=True,
        help="Device reports odometer field (vs total_odometer)",
    )
    fuel_reports_percentage = fields.Boolean(
        default=True,
        help="Device reports fuel_level (field 89) as percentage (0-100). If False, fuel_level is treated as liters.",
    )
    fuel_level_l_unit = fields.Selection(
        selection=[
            ("liters", "Liters"),
            ("deciliters", "Deciliters (÷10)"),
            ("centiliters", "Centiliters (÷100)"),
        ],
        default="deciliters",
        help="Unit for fuel_level_l field (CAN bus field 84). Teltonika CAN bus typically reports in deciliters.",
    )

    odometer_source = fields.Selection(
        selection=[
            ("none", "Not Available"),
            ("gps", "GPS Calculated (field 87)"),
            ("can", "CAN Bus (field 16)"),
            ("both", "Both Available (prefer GPS)"),
        ],
        default="gps",
        help="Which odometer source the device reports:\n"
        "- GPS Calculated: Teltonika field 87 (odometer in meters)\n"
        "- CAN Bus: Teltonika field 16 (total_odometer from vehicle)\n"
        "- Both: Device reports both sources",
    )

    fuel_source = fields.Selection(
        selection=[
            ("none", "Not Available"),
            ("percentage", "Percentage (field 89)"),
            ("volume", "Volume/Liters (field 84)"),
            ("both", "Both Available"),
        ],
        default="none",
        help="Which fuel data source the device reports:\n"
        "- Percentage: Teltonika field 89 (0-100%%)\n"
        "- Volume: Teltonika field 84 (in configured units)\n"
        "- Both: Device reports both percentage and volume",
    )

    speed_source = fields.Selection(
        selection=[
            ("none", "Not Available"),
            ("gps", "GPS Speed Only"),
            ("can", "CAN Bus Wheel Speed Only (field 81)"),
            ("both", "Both GPS and CAN Wheel Speed"),
        ],
        default="gps",
        help="Which speed data source the device reports:\n"
        "- GPS: Standard GPS-calculated speed\n"
        "- CAN: Teltonika field 81 (wheel speed from vehicle)\n"
        "- Both: Device reports both sources",
    )

    reports_ignition = fields.Boolean(
        default=False,
        help="Device reports ignition state (field 239). Indicates whether vehicle ignition is on/off.",
    )

    reports_engine_hours = fields.Boolean(
        default=False,
        help="Device reports engine total hours (field 102 from CAN bus).",
    )
    reports_engine_rpm = fields.Boolean(
        string="Reports Engine RPM",
        default=False,
        help="Device reports engine RPM (field 85 from CAN bus).",
    )
    reports_engine_temp = fields.Boolean(
        string="Reports Engine Temperature",
        default=False,
        help="Device reports engine temperature (field 115 from CAN bus).",
    )

    @api.constrains("speed_limit_warning", "speed_limit_alert", "speed_limit_critical")
    def _check_speed_limit_order(self) -> None:
        for config in self:
            if not (
                config.speed_limit_warning
                <= config.speed_limit_alert
                <= config.speed_limit_critical
            ):
                raise exceptions.ValidationError(
                    self.env._(
                        "Speed thresholds must be in ascending order: "
                        "warning ≤ alert ≤ critical."
                    )
                )

    _THRESHOLD_FIELDS = frozenset(
        {
            "motion_threshold_speed",
            "speed_limit_warning",
            "speed_limit_alert",
            "speed_limit_critical",
            "battery_threshold",
            "idle_threshold",
            "stationary_interval",
            "motion_threshold_distance",
        }
    )

    _ODOMETER_FIELDS = frozenset({"odometer_correction_factor", "reports_odometer"})

    _SPEED_LIMIT_FIELDS = frozenset(
        {"speed_limit_warning", "speed_limit_alert", "speed_limit_critical"}
    )

    def write(self, vals):
        result = super().write(vals)
        touched = set(vals)
        if self._THRESHOLD_FIELDS & touched:
            self._clear_threshold_cache()
        if self._ODOMETER_FIELDS & touched:
            self.env["device.data.log.gps"]._schedule_real_odometer_recompute(
                self.device_ids
            )
        if self._SPEED_LIMIT_FIELDS & touched:
            # speed_over_*_events are baked against the limits current at
            # refresh time; new limits rewrite settled history, so the report
            # must rebuild in full. Marking twice in one write is a no-op.
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result

    def _clear_threshold_cache(self) -> None:
        self.env.registry.clear_cache()

    _PROFILE_THRESHOLDS = {
        "battery_threshold": ("device_gps.battery_threshold_default", "20.0", float),
        "idle_threshold": ("device_gps.idle_threshold_default", "30", int),
        "motion_threshold_distance": (
            "device_gps.motion_threshold_distance_default",
            "50.0",
            float,
        ),
        "motion_threshold_speed": (
            "device_gps.motion_threshold_speed_default",
            "5.0",
            float,
        ),
        "speed_limit_warning": (
            "device_gps.speed_limit_warning_default",
            "80.0",
            float,
        ),
        "speed_limit_alert": ("device_gps.speed_limit_alert_default", "100.0", float),
        "speed_limit_critical": (
            "device_gps.speed_limit_critical_default",
            "120.0",
            float,
        ),
        "stationary_interval": ("device_gps.stationary_interval_default", "300", int),
    }

    @tools.ormcache("self.id", "name")
    def _profile_threshold(self, name):
        value = self[name]
        if value:
            return value
        key, default, cast = self._PROFILE_THRESHOLDS[name]
        raw = self.env.registry.settings.get(self.env, key, default=default)
        return cast(float(raw)) if cast is int else cast(raw)

    def _get_battery_threshold(self):
        return self._profile_threshold("battery_threshold")

    def _get_idle_threshold(self):
        return self._profile_threshold("idle_threshold")

    def _get_motion_threshold_distance(self):
        return self._profile_threshold("motion_threshold_distance")

    def _get_motion_threshold_speed(self):
        return self._profile_threshold("motion_threshold_speed")

    def _get_speed_limit_warning(self):
        return self._profile_threshold("speed_limit_warning")

    def _get_speed_limit_alert(self):
        return self._profile_threshold("speed_limit_alert")

    def _get_speed_limit_critical(self):
        return self._profile_threshold("speed_limit_critical")

    def _get_stationary_interval(self):
        return self._profile_threshold("stationary_interval")

    def get_corrected_odometer(self, raw_odometer):
        self.check_singleton()
        if not raw_odometer:
            return 0.0
        return super().get_corrected_odometer(raw_odometer)

    def real_odometer_from_raw(self, raw_odometer, device):
        self.check_singleton()
        corrected = self.get_corrected_odometer(raw_odometer)
        if not corrected:
            # The offset shifts a genuine reading; a payload with no odometer
            # must stay at 0 so NULLIF(real_odometer, 0) keeps excluding it.
            return 0.0
        return corrected + (device.odometer_initial_offset or 0)
