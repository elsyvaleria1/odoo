from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import SQL, frozendict

from odoo.addons.resource_asset_hr.models.resource_resource import live_custody_subquery

DEFAULT_TZ = "UTC"
MOVING_MIN_KMH = 5.0


class DeviceGpsSpeedDay(models.Model):
    _name = "device.gps.speed.day"
    _description = "Daily Speed per Vehicle"
    _auto = False
    _depends = frozendict(
        {
            "device.data.log.gps": ["device_id", "speed", "timestamp"],
            "device.device": ["asset_operator_id", "company_id", "config_id"],
            "device.profile": ["speed_limit_critical"],
            "res.company": ["partner_id"],
            "res.partner": ["tz"],
            "resource.config": ["company_id", "resource_calendar_id"],
            "resource.calendar": ["tz"],
            "resource.resource": ["kind_id", "tz"],
            "resource.gps.binding": [
                "device_id",
                "resource_id",
                "date_start",
                "date_end",
                "company_id",
            ],
            "resource.assignment": [
                "resource_id",
                "assignee_id",
                "custody_role",
                "date_start",
                "date_end",
                "active",
            ],
            "hr.employee": ["resource_id"],
        }
    )
    _order = "date desc, speed_max desc"
    _rec_name = "date"

    device_id = fields.Many2one(
        comodel_name="device.device",
        readonly=True,
    )
    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Vehicle",
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    date = fields.Date(readonly=True)
    speed_max = fields.Float(
        string="Max Speed (km/h)",
        digits=(6, 0),
        readonly=True,
    )
    speed_min = fields.Float(
        string="Min Speed (km/h)",
        digits=(6, 0),
        readonly=True,
        help="Lowest speed while moving (5 km/h or more); stops and GPS drift "
        "are not counted.",
    )
    speed_avg = fields.Float(
        string="Avg Speed (km/h)",
        digits=(6, 0),
        readonly=True,
        help="Mean of the readings while moving.",
    )
    speed_limit_critical = fields.Float(
        string="Critical Limit (km/h)",
        digits=(6, 0),
        readonly=True,
    )
    over_critical = fields.Boolean(
        string="Over Critical Limit",
        readonly=True,
    )
    first_seen = fields.Datetime(
        string="First Position",
        readonly=True,
    )
    last_seen = fields.Datetime(
        string="Last Position",
        readonly=True,
    )
    positions = fields.Integer(readonly=True)
    moving_positions = fields.Integer(readonly=True)

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            SQL(
                """
    CREATE OR REPLACE VIEW %(table)s AS
    SELECT MIN(l.id) AS id,
           l.device_id,
           op.employee_id AS operator_id,
           a.id AS asset_id,
           d.company_id,
           (l.timestamp AT TIME ZONE 'UTC'
                        AT TIME ZONE COALESCE(binding.tz, device_clock.tz))::date AS date,
           COALESCE(MAX(l.speed), 0) AS speed_max,
           COALESCE(MIN(l.speed) FILTER (WHERE l.speed >= %(moving)s), 0) AS speed_min,
           COALESCE(AVG(l.speed) FILTER (WHERE l.speed >= %(moving)s), 0) AS speed_avg,
           COALESCE(cfg.speed_limit_critical, 120.0) AS speed_limit_critical,
           COALESCE(MAX(l.speed), 0)
               > COALESCE(cfg.speed_limit_critical, 120.0) AS over_critical,
           MIN(l.timestamp) AS first_seen,
           MAX(l.timestamp) AS last_seen,
           COUNT(*) AS positions,
           COUNT(*) FILTER (WHERE l.speed >= %(moving)s) AS moving_positions
      FROM device_data_log_gps l
      JOIN device_device d ON d.id = l.device_id
      LEFT JOIN LATERAL (%(binding_query)s) binding ON TRUE
      LEFT JOIN resource_resource tracked_resource ON tracked_resource.id = binding.resource_id
      LEFT JOIN resource_resource a ON a.id = tracked_resource.id AND a.kind_id IS NOT NULL
      LEFT JOIN LATERAL %(operator_query)s ON TRUE
      LEFT JOIN device_profile cfg ON cfg.id = d.config_id
      LEFT JOIN (%(device_timezones)s) device_clock ON device_clock.device_id = d.id
     WHERE l.timestamp IS NOT NULL
     GROUP BY binding.binding_id, l.device_id, op.employee_id, a.id, d.company_id,
              cfg.speed_limit_critical, COALESCE(binding.tz, device_clock.tz),
              (l.timestamp AT TIME ZONE 'UTC'
                           AT TIME ZONE COALESCE(binding.tz, device_clock.tz))::date
                """,
                table=SQL.identifier(self._table),
                operator_query=SQL(
                    live_custody_subquery("operator", "a", "op", at="l.timestamp")
                ),
                binding_query=self.env["resource.gps.binding"]._at_query(
                    SQL("l.device_id"), SQL("l.timestamp")
                ),
                device_timezones=self.env["device.device"]._gps_timezone_query(),
                moving=MOVING_MIN_KMH,
            )
        )
