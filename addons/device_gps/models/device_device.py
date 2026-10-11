import logging
from datetime import timedelta

from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.wrappers import Response

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools import SQL

from odoo.addons.integration.tools.admission import Resolution

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

TRACKER_AUTH_MODE_PARAM = "device_gps.webhook_auth_mode"
TRACKER_MAX_ANONYMOUS_BODY = 256 * 1024
TRACKER_ACK = b"\x01"
TRACKER_NACK = b"\x00"


class DeviceDevice(models.Model):
    _inherit = "device.device"
    _receiver_privileges = ("device_gps.privilege_receive_fix",)

    def _gps_timezone(self):
        self.check_singleton()
        return (
            self.tracked_resource_id.tz
            or self.company_id.partner_id.tz
            or self.company_id.resource_calendar_id.tz
            or "UTC"
        )

    @api.model
    def _gps_timezone_query(self):
        return SQL(
            """
            SELECT d.id AS device_id,
                   COALESCE(p.tz, calendar.tz, 'UTC') AS tz
              FROM device_device d
              LEFT JOIN res_company c ON c.id = d.company_id
              LEFT JOIN res_partner p ON p.id = c.partner_id
              LEFT JOIN resource_config config ON config.company_id = c.id
              LEFT JOIN resource_calendar calendar ON calendar.id = config.resource_calendar_id
        """
        )

    tracked_resource_id = fields.One2one(
        comodel_name="resource.resource",
        inverse_name="gps_device_id",
        context={"active_test": False},
        help="Resource this device supplies GPS observations for, archived or not",
    )

    gps_receiver_key = fields.Char(
        string="GPS Receiver Key",
        index="btree_not_null",
        copy=False,
        help="Opaque source key sent in field 14 of the legacy tracker webhook. "
        "Teltonika defines that field as ICCID2, a SIM identity fragment, not "
        "hardware IMEI. This key selects a receiver; it grants no access. "
        "Duplicate keys are refused, including across companies and archives.",
    )

    is_gps_device = fields.Boolean(
        compute="_compute_is_gps_device",
        store=True,
    )
    gps_tracking_enabled = fields.Boolean(
        compute="_compute_gps_tracking_enabled",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        help="Enable continuous GPS tracking. Defaults to config setting but can be overridden.",
    )
    odometer_initial_offset = fields.Float(
        default=0.0,
        help="Add this value to corrected odometer (for pre-existing odometer values)",
    )

    fuel_tank_capacity = fields.Float(
        help="Total fuel tank capacity in liters (for percentage calculations)"
    )
    fuel_refill_threshold = fields.Float(
        default=5.0,
        help="Minimum fuel increase (in liters) to be considered a refueling event. "
        "Smaller increases are ignored as sensor noise.",
    )
    fuel_consumption_threshold = fields.Float(
        default=0.5,
        help="Minimum fuel decrease (in liters) to be counted as consumption. "
        "Filters sensor noise, sloshing, and temperature-based volume changes.",
    )
    fuel_theft_threshold = fields.Float(
        default=10.0,
        help="Minimum sudden fuel drop (in liters) to be flagged as a potential theft event. "
        "Should be significantly higher than fuel_consumption_threshold to avoid false positives.",
    )

    log_gps_ids = fields.One2many(
        comodel_name="device.data.log.gps",
        inverse_name="device_id",
        help="Historical GPS tracking points",
    )
    log_gps_count = fields.Integer(
        compute="_compute_log_gps_count",
        help="GPS points received in the last 24 hours.",
    )
    log_gps_last_id = fields.Many2one(comodel_name="device.data.log.gps")
    log_gps_last_latitude = fields.Float(
        related="log_gps_last_id.latitude",
        string="Last GPS Latitude",
        digits=(10, 7),
        readonly=True,
        help="Most recent GPS latitude from tracking point",
    )
    log_gps_last_longitude = fields.Float(
        related="log_gps_last_id.longitude",
        string="Last GPS Longitude",
        digits=(10, 7),
        readonly=True,
        help="Most recent GPS longitude from tracking point",
    )
    log_gps_last_speed = fields.Float(
        related="log_gps_last_id.speed",
        readonly=True,
        help="Most recent speed from tracking point",
    )
    log_gps_last_altitude = fields.Float(
        related="log_gps_last_id.altitude",
        readonly=True,
        help="Most recent altitude from tracking point",
    )
    log_gps_last_satellites = fields.Integer(
        related="log_gps_last_id.satellites",
        readonly=True,
        help="Most recent satellite count from tracking point",
    )
    log_gps_last_fuel_level_l = fields.Float(
        related="log_gps_last_id.fuel_level_l",
        readonly=True,
        help="Most recent fuel level in liters from tracking point (CAN bus field 84)",
    )
    log_gps_last_fuel_level = fields.Float(
        related="log_gps_last_id.fuel_level",
        readonly=True,
        help="Most recent fuel level percentage from tracking point (field 89)",
    )
    gps_ignition_state = fields.Boolean(
        related="log_gps_last_id.ignition",
        readonly=True,
        help="Current vehicle ignition state",
    )
    gps_movement_state = fields.Boolean(
        related="log_gps_last_id.movement",
        readonly=True,
        help="Current vehicle movement state",
    )
    gps_battery_level = fields.Float(
        compute="_compute_gps_battery_level",
        help="Battery level (voltage or percentage depending on device)",
    )
    kanban_dashboard = fields.Text(
        compute="_compute_kanban_dashboard",
        help="JSON data for kanban dashboard display",
    )
    kanban_color = fields.Integer(
        default=0,
        help="kanban_color for kanban card highlighting",
    )

    @api.model
    def _device_kind_categories(self, kind):
        codes = super()._device_kind_categories(kind)
        if kind == "gps":
            return [*codes, "gps_tracker"]
        return codes

    @api.depends("device_category_id", "device_category_id.code")
    def _compute_is_gps_device(self) -> None:
        for device in self:
            device.is_gps_device = device._is_device_kind("gps")

    @api.depends("config_id")
    def _compute_gps_tracking_enabled(self) -> None:
        for device in self:
            if device._origin.config_id != device.config_id:
                if device.config_id and hasattr(
                    device.config_id, "gps_tracking_enabled"
                ):
                    device.gps_tracking_enabled = device.config_id.gps_tracking_enabled
                else:
                    device.gps_tracking_enabled = True
            else:
                device.gps_tracking_enabled = device.gps_tracking_enabled

    @api.depends("log_gps_ids")
    def _compute_log_gps_count(self) -> None:
        if not self.ids:
            for device in self:
                device.log_gps_count = 0
            return
        since = fields.Datetime.now() - timedelta(hours=self._LOG_COUNT_WINDOW_HOURS)
        count_data = self.env["device.data.log.gps"]._read_group(
            [("device_id", "in", self.ids), ("timestamp", ">=", since)],
            ["device_id"],
            ["__count"],
        )
        count_map = {device.id: count for device, count in count_data}
        for device in self:
            device.log_gps_count = count_map.get(device.id, 0)

    @api.depends("log_gps_last_id", "log_gps_last_id.battery_voltage")
    def _compute_gps_battery_level(self) -> None:
        for device in self:
            if device.log_gps_last_id and device.log_gps_last_id.battery_voltage:
                device.gps_battery_level = device.log_gps_last_id.battery_voltage
            else:
                device.gps_battery_level = 0.0

    @api.depends(
        "is_gps_device",
        "log_gps_last_id",
        "log_gps_last_id.battery_voltage",
        "log_gps_last_id.ignition",
        "log_gps_last_id.movement",
        "log_gps_last_id.speed",
        "log_gps_last_id.satellites",
        "date_last_data_received",
        "connection_state",
        "gps_battery_level",
    )
    def _compute_kanban_dashboard(self) -> None:
        gps_device_ids = [d.id for d in self if d.is_gps_device]
        stats_by_device: dict[int, tuple] = {}
        if gps_device_ids:
            last_24h = fields.Datetime.now() - timedelta(hours=24)
            self.env.cr.execute(
                """
                SELECT
                    device_id,
                    COUNT(*),
                    COALESCE(AVG(speed), 0),
                    COALESCE(MAX(speed), 0),
                    COALESCE(MIN(NULLIF(real_odometer, 0))
                        FILTER (WHERE odometer_valid), 0),
                    COALESCE(MAX(real_odometer)
                        FILTER (WHERE odometer_valid), 0)
                FROM device_data_log_gps
                WHERE device_id = ANY(%s)
                  AND timestamp >= %s
                  AND timestamp IS NOT NULL
                GROUP BY device_id
                """,
                [gps_device_ids, last_24h],
            )
            for row in self.env.cr.fetchall():
                dev_id, cnt, avg_spd, max_spd, min_odo, max_odo = row
                stats_by_device[dev_id] = (cnt, avg_spd, max_spd, min_odo, max_odo)

        for device in self:
            if not device.is_gps_device:
                device.kanban_dashboard = json_dumps({})
                continue

            stats = stats_by_device.get(device.id, (0, 0.0, 0.0, 0.0, 0.0))
            total_logs_24h, avg_speed, max_speed, first_odometer, last_odometer = stats
            distance_24h = max(last_odometer - first_odometer, 0)

            last_update = device.date_last_data_received
            last_update_str = ""
            if last_update:
                seconds = (fields.Datetime.now() - last_update).total_seconds()
                if seconds < 3600:
                    last_update_str = self.env._(
                        "%(count)s min ago", count=int(seconds / 60)
                    )
                elif seconds < 86400:
                    last_update_str = self.env._(
                        "%(count)s hours ago", count=int(seconds / 3600)
                    )
                else:
                    last_update_str = self.env._(
                        "%(count)s days ago", count=int(seconds / 86400)
                    )

            connection_healthy = False
            if device.connection_state == "connected":
                connection_healthy = True
            elif device.connection_state == "error" and last_update:
                if (fields.Datetime.now() - last_update).total_seconds() < 3600:
                    connection_healthy = True

            battery_status = "unknown"
            if device.gps_battery_level > 0:
                if device.gps_battery_level >= 12.5:
                    battery_status = "good"
                elif device.gps_battery_level >= 11.8:
                    battery_status = "medium"
                else:
                    battery_status = "low"

            dashboard_data = {
                "total_logs_24h": total_logs_24h,
                "avg_speed": round(avg_speed, 1),
                "max_speed": round(max_speed, 1),
                "distance_24h": round(distance_24h, 1),
                "last_update_str": last_update_str,
                "connection_healthy": connection_healthy,
                "battery_status": battery_status,
                "battery_voltage": round(device.gps_battery_level, 1),
                "ignition_on": device.gps_ignition_state or False,
                "is_moving": device.gps_movement_state or False,
                "current_speed": round(device.log_gps_last_speed or 0, 1),
                "satellites": device.log_gps_last_satellites or 0,
                "show_company": len(self.env.companies) > 1,
            }

            device.kanban_dashboard = json_dumps(dashboard_data)

    def action_get_current_position(self):
        self.check_singleton()
        if not self.is_gps_device:
            raise UserError(
                self.env._("This action is only available for GPS devices.")
            )

        try:
            self.action_read_data()
            return self._notify(
                self.env._("GPS Position"),
                self.env._("Position request sent to %s") % self.name,
                "info",
            )

        except Exception as e:
            _logger.error("Error requesting position for %s: %s", self.name, e)
            raise UserError(self.env._("Error requesting position: %s") % str(e)) from e

    def action_start_tracking_gps(self):
        self.check_singleton()

        if not self.is_gps_device:
            raise UserError(
                self.env._("This action is only available for GPS devices.")
            )

        try:
            self.write({"gps_tracking_enabled": True})

            if self.connection_state != "connected":
                self.action_connect()

            self.message_post(body=self.env._("GPS tracking started"))

            return self._notify(
                self.env._("GPS Tracking"),
                self.env._("Tracking started for %s") % self.name,
            )

        except Exception as e:
            _logger.error("Error starting tracking for %s: %s", self.name, e)
            raise UserError(self.env._("Error starting tracking: %s") % str(e)) from e

    def action_stop_tracking_gps(self):
        self.check_singleton()
        if not self.is_gps_device:
            raise UserError(
                self.env._("This action is only available for GPS devices.")
            )

        try:
            self.write({"gps_tracking_enabled": False})

            self.message_post(body=self.env._("GPS tracking stopped"))

            return self._notify(
                self.env._("GPS Tracking"),
                self.env._("Tracking stopped for %s") % self.name,
                "info",
            )

        except Exception as e:
            _logger.error("Error stopping tracking for %s: %s", self.name, e)
            raise UserError(self.env._("Error stopping tracking: %s") % str(e)) from e

    @api.ondelete(at_uninstall=False)
    def _unlink_except_with_tracking_history(self) -> None:
        logs = self.env["device.data.log.gps"].sudo()
        with_history = self.browse(
            device.id
            for device in self
            if logs.search_count([("device_id", "=", device.id)], limit=1)
        )
        if with_history:
            raise UserError(
                self.env._(
                    "These devices still have GPS tracking history and cannot "
                    "be deleted: %(devices)s.\n\nArchive them instead: the "
                    "history is kept and the device stops being offered.",
                    devices=", ".join(with_history.mapped("display_name")),
                )
            )

    def action_view_logs_gps(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Tracking Points"),
            "type": "ir.actions.act_window",
            "res_model": "device.data.log.gps",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {
                "default_device_id": self.id,
                "search_default_last_week": 1,
            },
        }

    def action_view_on_map(self):
        self.check_singleton()
        if not self.log_gps_last_id:
            return self._notify(
                self.env._("GPS Position"),
                self.env._("No GPS data available for %s") % self.name,
                "warning",
            )
        return self.action_view_logs_gps()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_gps_history(self):
        if (
            self.env["resource.gps.binding"]
            .sudo()
            .search_count([("device_id", "in", self.ids)], limit=1)
        ):
            raise ValidationError(
                self.env._(
                    "Archive devices with GPS attachment history instead of deleting them."
                )
            )

    @api.constrains("company_id")
    def _check_tracked_resource_company(self):
        resources = self.sudo().mapped("tracked_resource_id")
        resources._check_company(["gps_device_id"])
        self._check_gps_history_company()

    def _check_gps_history_company(self, company_id=None):
        history = (
            self.env["resource.gps.binding"]
            .sudo()
            ._read_group([("device_id", "in", self.ids)], ["device_id", "company_id"])
        )
        for device, company in history:
            kept = device.company_id.id if company_id is None else company_id
            if company.id != kept:
                raise ValidationError(
                    self.env._(
                        "A device with GPS attachment history must retain its company."
                    )
                )

    def write(self, vals):
        if "company_id" in vals:
            self.check_access("write")
            self._check_gps_history_company(vals["company_id"])
        result = super().write(vals)
        if "odometer_initial_offset" in vals or "config_id" in vals:
            self.env["device.data.log.gps"]._schedule_real_odometer_recompute(self)
        if "company_id" in vals:
            self.env["device.data.log.gps.report"]._rolling_mark_stale()
        return result

    @api.model
    def _read_tracker_request(self) -> tuple | None:
        httprequest = request.httprequest
        httprequest.max_content_length = TRACKER_MAX_ANONYMOUS_BODY
        try:
            body = httprequest.get_data(cache=True)
        except RequestEntityTooLarge:
            return None
        try:
            json_data = json_loads(body) if body else None
        except ValueError:
            json_data = None
        if not isinstance(json_data, dict):
            return None
        payload = self.env["device.gps.data.processor"]._get_payload(json_data)
        if not payload:
            return None
        return payload, json_data

    @api.model
    def _receiver_for_tracker(self, **path_args):
        parsed = self._read_tracker_request()
        if parsed is None:
            return self.browse()
        payload, json_data = parsed
        device = self._get_tracker_by_receiver_key(payload.get("14"))
        if not device:
            return Resolution(self.browse(), claimed="unresolved GPS receiver key")
        return Resolution(device, {"payload": payload, "json_data": json_data})

    @api.model
    def _prepare_tracker_refusal_response(self, refused):
        return Response(TRACKER_NACK, status=200, mimetype="application/octet-stream")

    def _inbound_auth_mode(self, parameter_key=None):
        if parameter_key is None and self._is_device_kind("gps"):
            parameter_key = TRACKER_AUTH_MODE_PARAM
        return super()._inbound_auth_mode(parameter_key)

    @api.model
    def _normalize_tracker_key(self, value):
        if type(value) is int and value >= 0:
            value = str(value)
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            return None
        return value

    @api.model
    def _get_tracker_by_receiver_key(self, value):
        key = self._normalize_tracker_key(value)
        if key is None:
            _debug.logic("gps_receiver_resolution", result="invalid_key")
            return self.browse()
        devices = self.with_context(active_test=False).search(
            [("gps_receiver_key", "=", key)],
            limit=2,
        )
        accepted = len(devices) == 1 and devices.active
        _debug.logic(
            "gps_receiver_resolution",
            result="resolved" if accepted else "unresolved",
            candidate_ids=devices.ids,
        )
        return devices if accepted else self.browse()

    @api.model
    def _get_integrity_checks(self):
        checks = super()._get_integrity_checks()
        predicates = {
            "duplicate_gps_receiver_keys": SQL(
                "gps_receiver_key IN (SELECT gps_receiver_key FROM device_device "
                "WHERE gps_receiver_key IS NOT NULL AND gps_receiver_key != '' "
                "GROUP BY gps_receiver_key HAVING count(*) > 1)"
            ),
            "malformed_imeis": SQL(
                "imei IS NOT NULL AND imei != '' AND imei !~ '^[0-9]{15}$'"
            ),
        }
        checks.update(
            {
                reason: ("device_device", predicate)
                for reason, predicate in predicates.items()
            }
        )
        return checks

    def _cron_refresh_gps_pointers(self, lookback_minutes=60) -> None:
        since = fields.Datetime.now() - timedelta(minutes=lookback_minutes)
        self.env.cr.execute(
            """
            UPDATE device_device AS d
               SET log_gps_last_id = s.log_id,
                   date_last_data_received = s.received
              FROM (
                    SELECT l.device_id,
                           (array_agg(l.id ORDER BY l.timestamp DESC, l.id DESC))[1]
                               AS log_id,
                           max(l.create_date) AS received
                      FROM device_data_log_gps AS l
                     WHERE l.timestamp IS NOT NULL
                       AND l.timestamp > %s
                     GROUP BY l.device_id
                   ) AS s
             WHERE d.id = s.device_id
               AND (d.log_gps_last_id IS DISTINCT FROM s.log_id
                    OR d.date_last_data_received IS DISTINCT FROM s.received)
         RETURNING d.id
            """,
            [since],
        )
        moved_ids = [row[0] for row in self.env.cr.fetchall()]
        updated = len(moved_ids)

        self.env.cr.execute(
            """
            UPDATE device_device AS d
               SET connection_state = 'connected',
                   connection_state_message = NULL
              FROM (
                    SELECT DISTINCT l.device_id
                      FROM device_data_log_gps AS l
                     WHERE l.timestamp IS NOT NULL
                       AND l.timestamp > %s
                   ) AS s
             WHERE d.id = s.device_id
               AND d.connection_state IS DISTINCT FROM 'connected'
            """,
            [since],
        )
        reconnected = self.env.cr.rowcount

        if updated or reconnected:
            self.env["device.device"].invalidate_model(
                [
                    "log_gps_last_id",
                    "date_last_data_received",
                    "connection_state",
                    "connection_state_message",
                ],
            )
        if moved_ids:
            self.browse(moved_ids)._notify_gps_pointer_moved()
        if updated:
            _logger.info("GPS pointers refreshed for %d device(s)", updated)
        if reconnected:
            _logger.info("GPS devices marked connected: %d", reconnected)

    def _notify_gps_pointer_moved(self):
        pass
