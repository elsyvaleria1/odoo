from odoo import api, fields, models
from odoo.tools import SQL

from .device_gps_speed_day import MOVING_MIN_KMH
from odoo.addons.resource_asset_hr.models.resource_resource import live_custody_subquery


class DeviceClientVisit(models.Model):
    _inherit = "device.client.visit"

    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Operator",
        compute="_compute_visit_target",
        compute_sudo=False,
        help="Operator assigned to the vehicle at arrival.",
    )
    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Vehicle",
        compute="_compute_visit_target",
        compute_sudo=False,
        help="Vehicle observed by the tracker when this parcel stay began.",
    )
    trip_speed_max = fields.Float(
        string="Trip Max Speed (km/h)",
        digits=(6, 0),
        compute="_compute_trip_speed",
        help="Highest speed on the way to this parcel: from the departure "
        "of the device's previous visit (or the first position of the day) "
        "to this arrival.",
    )
    trip_speed_min = fields.Float(
        string="Trip Min Speed (km/h)",
        digits=(6, 0),
        compute="_compute_trip_speed",
        help="Lowest speed while moving on the way to this parcel.",
    )
    trip_speed_avg = fields.Float(
        string="Trip Avg Speed (km/h)",
        digits=(6, 0),
        compute="_compute_trip_speed",
    )

    @api.depends("device_id", "arrival")
    def _compute_visit_target(self):
        for visit in self:
            visit.operator_id = False
            visit.asset_id = False
        saved = self.filtered(lambda visit: isinstance(visit.id, int))
        if not saved:
            return
        saved.check_access("read")
        saved.flush_recordset(["device_id", "arrival"])
        self.env["resource.gps.binding"].flush_model()
        self.env["resource.assignment"].flush_model()
        self.env.cr.execute(
            SQL(
                """
            SELECT v.id, a.id AS asset_id, op.employee_id
              FROM device_client_visit v
              LEFT JOIN LATERAL (%(binding)s) binding ON TRUE
              LEFT JOIN resource_resource a ON a.id = binding.resource_id AND a.kind_id IS NOT NULL
              LEFT JOIN LATERAL %(operator)s ON TRUE
             WHERE v.id = ANY(%(ids)s)
            """,
                binding=self.env["resource.gps.binding"]._at_query(
                    SQL("v.device_id"), SQL("v.arrival")
                ),
                operator=SQL(
                    live_custody_subquery("operator", "a", "op", at="v.arrival")
                ),
                ids=saved.ids,
            )
        )
        for row in self.env.cr.dictfetchall():
            visit = saved.browse(row["id"])
            visit.asset_id = row["asset_id"]
            visit.operator_id = row["employee_id"]

    @api.depends("device_id", "arrival")
    def _compute_trip_speed(self) -> None:
        by_visit = self._trip_speed_by_visit()
        for visit in self:
            top, low, avg = by_visit.get(visit.id, (0.0, 0.0, 0.0))
            visit.trip_speed_max = top
            visit.trip_speed_min = low
            visit.trip_speed_avg = avg

    def _trip_speed_by_visit(self) -> dict:
        ids = [visit.id for visit in self if isinstance(visit.id, int)]
        if not ids:
            return {}
        self.check_access("read")
        self.env["device.data.log.gps"].check_access("read")
        self.flush_recordset(["device_id", "arrival", "departure"])
        self.env["device.data.log.gps"].flush_model(["device_id", "timestamp", "speed"])
        self.env["resource.gps.binding"].flush_model()
        self.env["resource.resource"].flush_model(["tz"])
        self.env.cr.execute(
            SQL(
                """
            SELECT v.id,
                   COALESCE(MAX(l.speed), 0),
                   COALESCE(MIN(l.speed) FILTER (WHERE l.speed >= %(moving)s), 0),
                   COALESCE(AVG(l.speed) FILTER (WHERE l.speed >= %(moving)s), 0)
              FROM device_client_visit v
              LEFT JOIN LATERAL (%(binding)s) binding ON TRUE
              LEFT JOIN (%(timezones)s) clock ON clock.device_id = v.device_id
              LEFT JOIN LATERAL (
                    SELECT GREATEST(
                               COALESCE(MAX(prev.departure), ((v.arrival AT TIME ZONE 'UTC' AT TIME ZONE COALESCE(binding.tz, clock.tz))::date::timestamp AT TIME ZONE COALESCE(binding.tz, clock.tz)) AT TIME ZONE 'UTC'),
                               ((v.arrival AT TIME ZONE 'UTC' AT TIME ZONE COALESCE(binding.tz, clock.tz))::date::timestamp AT TIME ZONE COALESCE(binding.tz, clock.tz)) AT TIME ZONE 'UTC'
                           ) AS since
                      FROM device_client_visit prev
                     WHERE prev.device_id = v.device_id
                       AND prev.departure IS NOT NULL
                       AND prev.departure <= v.arrival
                       AND prev.id <> v.id
                   ) b ON TRUE
              LEFT JOIN device_data_log_gps l
                ON l.device_id = v.device_id
               AND l.timestamp > b.since
               AND l.timestamp <= v.arrival
               AND (binding.date_start IS NULL OR l.timestamp >= binding.date_start)
             WHERE v.id = ANY(%(ids)s)
             GROUP BY v.id
            """,
                ids=ids,
                moving=MOVING_MIN_KMH,
                binding=self.env["resource.gps.binding"]._at_query(
                    SQL("v.device_id"), SQL("v.arrival")
                ),
                timezones=self.env["device.device"]._gps_timezone_query(),
            )
        )
        return {
            visit_id: (round(top), round(low), round(avg))
            for visit_id, top, low, avg in self.env.cr.fetchall()
        }
