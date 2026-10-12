from datetime import timedelta

from odoo import api, fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import SQL, frozendict

from odoo.addons.resource_asset_hr.models.resource_resource import live_custody_subquery

EVENT_GAP = timedelta(minutes=3)
NEARBY_CLIENT_M = 3000


class DeviceGpsSpeedEvent(models.Model):
    _name = "device.gps.speed.event"
    _description = "Speeding Event"
    _auto = False
    _depends = frozendict(
        {
            "device.data.log.gps": ["device_id", "speed", "the_point", "timestamp"],
            "device.device": ["asset_operator_id", "company_id", "config_id"],
            "device.geo.fence": ["active", "area_type", "partner_id", "the_geom"],
            "device.profile": [
                "speed_limit_alert",
                "speed_limit_critical",
                "speed_limit_warning",
            ],
            "device.state.boundary": ["geom", "state_id"],
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
    _order = "start desc"
    _rec_name = "start"

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
    start = fields.Datetime(readonly=True)
    end = fields.Datetime(readonly=True)
    date = fields.Date(readonly=True)
    duration_min = fields.Float(
        string="Duration (min)",
        digits=(6, 1),
        readonly=True,
    )
    speed_max = fields.Float(
        string="Max Speed (km/h)",
        digits=(6, 0),
        readonly=True,
    )
    speed_avg = fields.Float(
        string="Avg Speed (km/h)",
        digits=(6, 0),
        readonly=True,
    )
    speed_limit = fields.Float(
        string="Limit Exceeded (km/h)",
        digits=(6, 0),
        readonly=True,
        help="The highest of the device's limits that the burst went over.",
    )
    level = fields.Selection(
        selection=[
            ("warning", "Warning"),
            ("alert", "Alert"),
            ("critical", "Critical"),
        ],
        readonly=True,
    )
    positions = fields.Integer(readonly=True)
    distance_km = fields.Float(
        string="Distance (km)",
        digits=(8, 1),
        readonly=True,
    )
    nearby_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Nearest Client",
        readonly=True,
    )
    nearby_geofence_id = fields.Many2one(
        comodel_name="device.geo.fence",
        string="Nearest Parcel",
        readonly=True,
    )
    nearby_distance_m = fields.Integer(
        string="Distance to Parcel (m)",
        readonly=True,
    )
    state_id = fields.Many2one(
        comodel_name="res.country.state",
        readonly=True,
    )
    latitude = fields.Float(
        digits=(9, 6),
        readonly=True,
    )
    longitude = fields.Float(
        digits=(9, 6),
        readonly=True,
    )
    place = fields.Char(compute="_compute_place")

    @api.depends(
        "nearby_geofence_id", "nearby_partner_id", "nearby_distance_m", "state_id"
    )
    def _compute_place(self) -> None:
        for event in self:
            parts = []
            if event.nearby_geofence_id:
                where = event.nearby_geofence_id.name
                if event.nearby_partner_id:
                    where = f"{where} ({event.nearby_partner_id.name})"
                if event.nearby_distance_m:
                    where = f"{where}, a {event.nearby_distance_m} m"
                parts.append(where)
            if event.state_id:
                parts.append(event.state_id.name)
            if not parts:
                parts.append(f"{event.latitude:.5f}, {event.longitude:.5f}")
            event.place = " · ".join(parts)

    def action_view_trail(self):
        self.check_singleton()
        wizard = self.env["wizard.device.device.view.trail"].create(
            {
                "selection_mode": "device",
                "device_ids": [fields.Command.set([self.device_id.id])],
                "date_from": self.start - timedelta(minutes=5),
                "date_to": self.end + timedelta(minutes=5),
            }
        )
        return wizard.action_generate_trails()

    @api.model
    def _get_recent_events(self, since):
        self.env.cr.execute(
            SQL(
                "SELECT * FROM (%s) e WHERE e.start >= %s",
                self._get_events_query(since - EVENT_GAP),
                since,
            )
        )
        events = self.browse()
        for row in self.env.cr.dictfetchall():
            del row["id"]
            events |= self.new(row)
        return events

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            SQL(
                "CREATE OR REPLACE VIEW %s AS %s",
                SQL.identifier(self._table),
                self._get_events_query(),
            )
        )

    @api.model
    def _get_events_query(self, positions_since=None):
        return SQL(
            """
    WITH fast AS (
        SELECT binding.binding_id, l.id, l.device_id, l.timestamp, l.speed, l.the_point,
               COALESCE(cfg.speed_limit_warning, 80.0) AS lim_warning,
               COALESCE(cfg.speed_limit_alert, 100.0) AS lim_alert,
               COALESCE(cfg.speed_limit_critical, 120.0) AS lim_critical,
               op.employee_id AS asset_operator_id, a.id AS asset_id, d.company_id
          FROM device_data_log_gps l
          JOIN device_device d ON d.id = l.device_id
          LEFT JOIN LATERAL (%(binding_query)s) binding ON TRUE
      LEFT JOIN resource_resource tracked_resource ON tracked_resource.id = binding.resource_id
      LEFT JOIN resource_resource a ON a.id = tracked_resource.id AND a.kind_id IS NOT NULL
          LEFT JOIN LATERAL %(operator_query)s ON TRUE
      LEFT JOIN device_profile cfg ON cfg.id = d.config_id
         WHERE l.speed > COALESCE(cfg.speed_limit_warning, 80.0)
           AND l.timestamp IS NOT NULL
           %(positions_since)s
    ),
    marked AS (
        SELECT *,
               CASE WHEN timestamp - LAG(timestamp) OVER w > %(gap)s
                      OR LAG(timestamp) OVER w IS NULL
                    THEN 1 ELSE 0 END AS starts
          FROM fast
        WINDOW w AS (PARTITION BY device_id, binding_id, asset_operator_id ORDER BY timestamp, id)
    ),
    grouped AS (
        SELECT *, SUM(starts) OVER (PARTITION BY device_id, binding_id, asset_operator_id
                                    ORDER BY timestamp, id) AS grp
          FROM marked
    ),
    events AS (
        SELECT MIN(id) AS id, device_id, grp,
               MIN(timestamp) AS start, MAX(timestamp) AS "end",
               MAX(speed) AS speed_max, AVG(speed) AS speed_avg,
               COUNT(*) AS positions,
               MIN(lim_warning) AS lim_warning, MIN(lim_alert) AS lim_alert,
               MIN(lim_critical) AS lim_critical,
               MIN(asset_operator_id) AS operator_id, MIN(asset_id) AS asset_id,
               MIN(company_id) AS company_id,
               (ARRAY_AGG(the_point ORDER BY timestamp, id)
                   FILTER (WHERE the_point IS NOT NULL))[1] AS first_point,
               ST_Length(ST_MakeLine(the_point ORDER BY timestamp, id)::geography)
                   / 1000.0 AS distance_km
          FROM grouped
         GROUP BY device_id, binding_id, asset_operator_id, grp
    )
    SELECT e.id, e.device_id, e.operator_id, e.asset_id, e.company_id,
           e.start, e."end", e.start::date AS date,
           EXTRACT(EPOCH FROM (e."end" - e.start)) / 60.0 AS duration_min,
           e.speed_max, e.speed_avg, e.positions, e.distance_km,
           CASE WHEN e.speed_max > e.lim_critical THEN 'critical'
                WHEN e.speed_max > e.lim_alert THEN 'alert'
                ELSE 'warning' END AS level,
           CASE WHEN e.speed_max > e.lim_critical THEN e.lim_critical
                WHEN e.speed_max > e.lim_alert THEN e.lim_alert
                ELSE e.lim_warning END AS speed_limit,
           f.partner_id AS nearby_partner_id, f.id AS nearby_geofence_id,
           f.dist AS nearby_distance_m,
           s.state_id,
           ST_Y(e.first_point) AS latitude, ST_X(e.first_point) AS longitude
      FROM events e
      LEFT JOIN LATERAL (
            -- the_geom is Web Mercator; comparing there keeps its GiST index
            -- (cosd() converts the metres, see device.device), and the true
            -- distance is computed only for the one row that survives.
            SELECT f.id, f.partner_id,
                   ROUND(ST_Distance(ST_Transform(f.the_geom, 4326)::geography,
                                     e.first_point::geography))::int AS dist
              FROM device_geo_fence f
             WHERE f.area_type = 'parcel' AND f.active
               AND f.partner_id IS NOT NULL
               AND e.first_point IS NOT NULL
               AND ST_DWithin(f.the_geom, ST_Transform(e.first_point, 3857),
                              %(nearby)s / cosd(ST_Y(e.first_point)))
             ORDER BY ST_Distance(f.the_geom, ST_Transform(e.first_point, 3857))
             LIMIT 1
           ) f ON TRUE
      LEFT JOIN LATERAL (
            SELECT b.state_id
              FROM device_state_boundary b
             WHERE e.first_point IS NOT NULL
               AND ST_Contains(b.geom, e.first_point)
             LIMIT 1
           ) s ON TRUE
            """,
            binding_query=self.env["resource.gps.binding"]._at_query(
                SQL("l.device_id"), SQL("l.timestamp")
            ),
            operator_query=SQL(
                live_custody_subquery("operator", "a", "op", at="l.timestamp")
            ),
            positions_since=SQL("AND l.timestamp >= %s", positions_since)
            if positions_since
            else SQL(),
            gap=EVENT_GAP,
            nearby=NEARBY_CLIENT_M,
        )
