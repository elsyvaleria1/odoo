from datetime import UTC, datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from ..tools.actions import prepare_gps_device_action
from ..tools.readings import OdometerReading

_debug = DebugLog(__name__)

GPS_VALID_ODOMETER = [("odometer_valid", "=", True), ("real_odometer", ">", 0)]
GPS_ODOMETER_MAX_GAP = timedelta(minutes=30)


def _utc_instant(moment):
    return moment.astimezone(UTC).replace(tzinfo=None) if moment.tzinfo else moment


class MixinGps(models.AbstractModel):

    _name = "mixin.gps"
    _description = "GPS Observation Mixin"

    gps_device_id = fields.Many2one(
        comodel_name="device.device",
        string="GPS Device",
        copy=False,
        domain=[("is_gps_device", "=", True)],
        help="Device supplying GPS observations for this resource",
    )
    gps_observation_id = fields.Many2one(
        comodel_name="device.data.log.gps",
        compute="_compute_gps_observation",
        compute_sudo=False,
        copy=False,
        groups="device_gps.group_device_gps_user",
    )

    @api.depends(
        "gps_device_id",
        "gps_device_id.log_gps_last_id",
        "gps_device_id.log_gps_last_id.timestamp",
    )
    def _compute_gps_observation(self):
        resources = {record: record._gps_resource() for record in self}
        current = self.env["resource.gps.binding"]._current_periods(
            self.env["resource.resource"].browse(
                sorted({resource.id for resource in resources.values() if resource})
            )
        )
        now = fields.Datetime.now()
        for record in self:
            log = record.gps_device_id.log_gps_last_id
            valid = bool(
                log
                and log.timestamp
                and log.timestamp <= now
                and log.device_id == record.gps_device_id
            )
            resource = resources[record]
            if valid and resource:
                period = current.get(resource.id)
                valid = bool(
                    period
                    and period[0] == record.gps_device_id.id
                    and (not period[1] or log.timestamp >= period[1])
                )
            record.gps_observation_id = (
                log if valid else self.env["device.data.log.gps"]
            )

    gps_battery_level = fields.Float(
        related="gps_device_id.gps_battery_level",
        string="GPS Battery",
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_connection_state = fields.Selection(
        related="gps_device_id.connection_state",
        string="GPS Connection",
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_current_speed = fields.Float(
        related="gps_observation_id.speed",
        string="Speed (km/h)",
        depends=["gps_observation_id", "gps_device_id.log_gps_last_id.speed"],
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_fuel_level_l = fields.Float(
        related="gps_observation_id.fuel_level_l",
        string="Fuel Level (L)",
        depends=["gps_observation_id", "gps_device_id.log_gps_last_id.fuel_level_l"],
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_fuel_level = fields.Float(
        related="gps_observation_id.fuel_level",
        string="Fuel Level (%)",
        depends=["gps_observation_id", "gps_device_id.log_gps_last_id.fuel_level"],
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_date_last_data = fields.Datetime(
        related="gps_observation_id.timestamp",
        string="GPS Last Update",
        depends=["gps_observation_id", "gps_device_id.log_gps_last_id.timestamp"],
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_ignition_state = fields.Boolean(
        related="gps_observation_id.ignition",
        string="Ignition",
        depends=["gps_observation_id", "gps_device_id.log_gps_last_id.ignition"],
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_movement_state = fields.Boolean(
        related="gps_observation_id.movement",
        string="Moving",
        depends=["gps_observation_id", "gps_device_id.log_gps_last_id.movement"],
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )
    gps_tracking_enabled = fields.Boolean(
        related="gps_device_id.gps_tracking_enabled",
        string="Tracking Enabled",
        compute_sudo=False,
        groups="device_gps.group_device_gps_user",
    )

    def _gps_resource(self):
        self.check_singleton()
        return self.env["resource.resource"]

    def _gps_device_ids(self):
        resource = self._gps_resource()
        if resource:
            return sorted(
                {
                    device_id
                    for device_id, _start, _end in self.env[
                        "resource.gps.binding"
                    ]._periods(resource)
                }
            )
        return self.gps_device_id.ids

    def _gps_observation_domain(self):
        resource = self._gps_resource()
        if resource:
            return self.env["resource.gps.binding"]._observation_domain(resource)
        return (
            Domain("device_id", "=", self.gps_device_id.id)
            if self.gps_device_id
            else Domain.FALSE
        )

    def _gps_odometer_reading(
        self,
        moment: datetime | None = None,
        *,
        before: timedelta | None = None,
        after: timedelta = timedelta(0),
    ) -> OdometerReading | None:
        self.check_singleton()
        self.check_access("read")
        Log = self.env["device.data.log.gps"].with_privilege(
            "device_gps.privilege_read_resource_odometer",
            reason="a resource reads its own GPS odometer",
        )
        moment = _utc_instant(moment) if moment is not None else None
        as_of = moment or fields.Datetime.now()
        domain = [*self._gps_observation_domain(), *GPS_VALID_ODOMETER]
        earlier = [*domain, ("timestamp", "<=", as_of)]
        if before is not None:
            earlier.append(("timestamp", ">=", as_of - before))
        readings = Log.search(earlier, order="timestamp desc, id desc", limit=1)
        if moment and after:
            readings |= Log.search(
                [
                    *domain,
                    ("timestamp", ">", moment),
                    ("timestamp", "<=", moment + after),
                ],
                order="timestamp asc, id asc",
                limit=1,
            )
        if not readings:
            return None
        log = (
            min(readings, key=lambda log: abs(log.timestamp - moment))
            if moment
            else readings
        )
        return OdometerReading(value=log.real_odometer, timestamp=log.timestamp)

    def _get_current_gps_odometer(self) -> float:
        reading = self._gps_odometer_reading()
        _debug.logic(
            "gps_odometer_read",
            resource=self,
            device=self.gps_device_id,
            found=bool(reading),
        )
        return reading.value if reading else 0.0

    def _gps_odometer_at(self, moment, max_gap=GPS_ODOMETER_MAX_GAP) -> float:
        self.check_singleton()
        if not moment:
            return 0.0
        reading = self._gps_odometer_reading(moment, before=max_gap, after=max_gap)
        return reading.value if reading else 0.0

    def _gps_position(self, moment=None, max_age=None):
        self.check_singleton()
        self.check_access("read")
        Log = self.env["device.data.log.gps"]
        moment = _utc_instant(moment or fields.Datetime.now())
        domain = [
            *self._gps_observation_domain(),
            ("timestamp", "<=", moment),
            "|",
            ("latitude", "!=", 0),
            ("longitude", "!=", 0),
        ]
        if max_age is not None:
            domain.append(("timestamp", ">=", moment - max_age))
        return Log.search(domain, order="timestamp desc, id desc", limit=1)

    def action_view_gps_device(self):
        self.check_access("read")
        return prepare_gps_device_action(self)

    def action_view_tracking_history(self):
        self.check_singleton()
        self.check_access("read")
        domain = self._gps_observation_domain()
        if domain.is_false():
            raise ValidationError(self.env._("No GPS device assigned to this resource"))
        return {
            "name": self.env._("Tracking History: %s") % self.display_name,
            "type": "ir.actions.act_window",
            "res_model": "device.data.log.gps",
            "view_mode": "list,form",
            "domain": list(domain),
            "context": {
                "default_device_id": self.gps_device_id.id,
                "search_default_last_week": 1,
            },
        }
