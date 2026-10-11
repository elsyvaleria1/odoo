import logging
import time as time_module
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from .device_gps_place import PLACE_REUSE_M
from .device_gps_speed_day import DEFAULT_TZ, MOVING_MIN_KMH
from odoo.addons.resource_asset_hr.models.resource_resource import live_custody_subquery

_logger = logging.getLogger(__name__)

MIN_STOP_MINUTES = 5
STOP_RADIUS_M = 200
AT_GEOFENCE_M = 50
NEARBY_CLIENT_M = 3000
SCAN_LOOKBACK = timedelta(hours=12)
ONGOING_MAX_AGE = timedelta(days=7)
LONG_PARK_MINUTES = 20
MARKED_WITHIN_M = 50
COLOR_MARKED = "#198754"
COLOR_TO_MARK = "#fd7e14"
COLOR_SHORT_STOP = "#0d6efd"
MAX_PLACE_LOOKUPS = 30


class DeviceGpsStop(models.Model):

    _name = "device.gps.stop"
    _description = "Vehicle Stop"
    _order = "date desc, asset_id, arrival"
    _rec_name = "arrival"

    kind = fields.Selection(
        selection=[
            ("stop", "Stop"),
            ("no_signal", "No Positions"),
        ],
        default="stop",
        readonly=True,
        required=True,
        help="No Positions: the vehicle's tracker sent nothing that day, so "
        "the vehicle is listed even though there is no stop to show.",
    )
    device_id = fields.Many2one(
        comodel_name="device.device",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    asset_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Vehicle",
        readonly=True,
    )
    operator_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
        help="The vehicle's operator when the stop was recorded.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    date = fields.Date(
        index=True,
        readonly=True,
        required=True,
        help="Local day of the arrival.",
    )
    arrival = fields.Datetime(readonly=True)
    departure = fields.Datetime(
        readonly=True,
        help="First moving position after the stop. Empty while the vehicle "
        "is still there.",
    )
    ongoing = fields.Boolean(readonly=True)
    duration_hours = fields.Float(
        string="Duration (h)",
        readonly=True,
        help="Arrival to departure; up to the last refresh while ongoing.",
    )
    positions = fields.Integer(readonly=True)
    latitude = fields.Float(
        digits=(9, 6),
        readonly=True,
    )
    longitude = fields.Float(
        digits=(9, 6),
        readonly=True,
    )
    geofence_id = fields.Many2one(
        comodel_name="device.geo.fence",
        string="Geofence",
        readonly=True,
        help=f"Geofence the stop was on or within {AT_GEOFENCE_M} m of.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Client",
        readonly=True,
        help="Client of the geofence the stop was on.",
    )
    nearby_geofence_id = fields.Many2one(
        comodel_name="device.geo.fence",
        string="Nearest Client Parcel",
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
    last_seen = fields.Datetime(
        string="Last Position",
        readonly=True,
        help="No Positions rows: the tracker's last position before that day.",
    )
    the_point = fields.GeoPoint(
        string="Place on Map",
        readonly=True,
        srid=4326,
    )
    map_color = fields.Char(
        compute="_compute_map_color",
        help="Green at a client or internal geofence; orange at a place to "
        "mark; blue for a short stop anywhere else.",
    )
    to_mark = fields.Boolean(
        string="To Mark",
        compute="_compute_to_mark",
        search="_search_to_mark",
        help=f"The vehicle stayed more than {LONG_PARK_MINUTES} minutes at a "
        "place with no client geofence and no internal one. Stays set until "
        "someone gives the geofence a client or draws one there.",
    )
    place_id = fields.Many2one(
        comodel_name="device.gps.place",
        string="OpenStreetMap Place",
        readonly=True,
        help="Outside every geofence: what the place is, as OpenStreetMap "
        "names it -- a fonda, a gas station, a street.",
    )
    place = fields.Char(compute="_compute_place")
    map_url = fields.Char(
        string="Map",
        compute="_compute_map_url",
    )

    @api.depends(
        "kind",
        "geofence_id",
        "place_id",
        "partner_id",
        "nearby_geofence_id",
        "nearby_distance_m",
        "state_id",
        "latitude",
        "longitude",
    )
    def _compute_place(self):
        for stop in self:
            if stop.kind == "no_signal":
                stop.place = False
                continue
            parts = []
            if stop.geofence_id:
                where = stop.geofence_id.name
                if stop.partner_id:
                    where = f"{where} ({stop.partner_id.name})"
                parts.append(where)
            elif stop.place_id:
                parts.append(stop.place_id.label)
            if not stop.geofence_id and stop.nearby_geofence_id:
                parts.append(
                    self.env._(
                        "%(distance)s m from %(parcel)s (%(client)s)",
                        distance=stop.nearby_distance_m,
                        parcel=stop.nearby_geofence_id.name,
                        client=stop.nearby_geofence_id.partner_id.name,
                    )
                )
            if not parts and not stop.state_id:
                parts.append(self.env._("Outside geofences"))
            if stop.state_id:
                parts.append(stop.state_id.name)
            stop.place = " · ".join(parts)

    @api.model
    def _to_mark_sql(self, alias):
        return SQL(
            """
            %(s)s.kind = 'stop'
            AND %(s)s.duration_hours * 60 > %(minutes)s
            AND %(s)s.the_point IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM device_geo_fence f
                 WHERE f.active
                   AND (f.partner_id IS NOT NULL OR f.usage = 'internal')
                   AND ST_DWithin(f.the_geom, ST_Transform(%(s)s.the_point, 3857),
                                  %(within)s / cosd(%(s)s.latitude)))
            """,
            s=SQL.identifier(alias),
            minutes=LONG_PARK_MINUTES,
            within=MARKED_WITHIN_M,
        )

    def _flush_to_mark_inputs(self):
        self.env["device.geo.fence"].flush_model(
            ["active", "partner_id", "usage", "the_geom"]
        )
        self.flush_model(
            ["kind", "duration_hours", "the_point", "latitude", "geofence_id"]
        )

    def _to_mark_ids(self, ids=None):
        self._flush_to_mark_inputs()
        self.env.cr.execute(
            SQL(
                "SELECT s.id FROM device_gps_stop s WHERE %s%s",
                self._to_mark_sql("s"),
                SQL(" AND s.id = ANY(%s)", list(ids)) if ids is not None else SQL(),
            )
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _compute_to_mark(self):
        pending = set(self._to_mark_ids(self.ids))
        for stop in self:
            stop.to_mark = stop.id in pending

    def _search_to_mark(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        positive = (operator == "in") == (True in value)
        return [("id", "in" if positive else "not in", self._to_mark_ids())]

    @api.depends("to_mark", "geofence_id", "duration_hours")
    def _compute_map_color(self):
        for stop in self:
            if stop.to_mark:
                stop.map_color = COLOR_TO_MARK
            elif stop.duration_hours * 60 > LONG_PARK_MINUTES or stop.geofence_id:
                stop.map_color = COLOR_MARKED
            else:
                stop.map_color = COLOR_SHORT_STOP

    @api.depends("kind", "latitude", "longitude")
    def _compute_map_url(self):
        for stop in self:
            stop.map_url = (
                f"https://www.google.com/maps?q={stop.latitude:.6f},{stop.longitude:.6f}"
                if stop.kind == "stop"
                else False
            )

    def action_view_trail(self):
        self.check_singleton()
        end = self.departure or fields.Datetime.now()
        wizard = self.env["wizard.device.device.view.trail"].create(
            {
                "selection_mode": "device",
                "device_ids": [fields.Command.set([self.device_id.id])],
                "date_from": self.arrival - timedelta(minutes=15),
                "date_to": end + timedelta(minutes=15),
            }
        )
        return wizard.action_generate_trails()


    @api.model
    def _local_day_start_utc(self, day, timezone=None):
        start = datetime.combine(
            day,
            time(),
            tzinfo=ZoneInfo(timezone or self.env.company.partner_id.tz or DEFAULT_TZ),
        )
        return start.astimezone(UTC).replace(tzinfo=None)

    @api.model
    def _local_today(self, timezone=None):
        now = fields.Datetime.now().replace(tzinfo=UTC)
        return now.astimezone(
            ZoneInfo(timezone or self.env.company.partner_id.tz or DEFAULT_TZ)
        ).date()

    @api.model
    def _mark_dates_stale(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "device.gps.stop.dates_stale", "1"
        )

    @api.model
    def _cron_refresh(self):
        devices = self.env["device.device"].search([("is_gps_device", "=", True)])
        parameters = self.env["ir.config_parameter"].sudo()
        rebuild = parameters.get_param("device.gps.stop.dates_stale") == "1"
        if rebuild:
            parameters.set_param("device.gps.stop.dates_stale", "0")
        settled_all = (
            self.search([("device_id", "in", devices.ids)])
            if rebuild
            else self.browse()
        )
        for timezone, group in devices.grouped(
            lambda device: device._gps_timezone()
        ).items():
            today = self._local_today(timezone)
            date_from = today - timedelta(days=1)
            if rebuild:
                settled = settled_all.filtered_domain([("device_id", "in", group.ids)])
                if settled:
                    date_from = min(
                        date_from, min(settled.mapped("date")) - timedelta(days=2)
                    )
                    settled.unlink()
            self._refresh(date_from, today, devices=group)
            self._name_places(today - ONGOING_MAX_AGE, devices=group)

    @api.model
    def _name_places(self, since, devices=None, limit=MAX_PLACE_LOOKUPS):
        stops = self.search(
            [
                ("kind", "=", "stop"),
                ("geofence_id", "=", False),
                ("place_id", "=", False),
                ("date", ">=", since),
                *([("device_id", "in", devices.ids)] if devices is not None else []),
            ],
            order="ongoing desc, duration_hours desc, arrival desc",
        )
        places = self.env["device.gps.place"]
        lookups = 0
        for stop in stops:
            place = places._find_near(stop.latitude, stop.longitude)
            if not place:
                if lookups >= limit:
                    continue
                if lookups:
                    time_module.sleep(1)
                lookups += 1
                try:
                    place = places._look_up(stop.latitude, stop.longitude)
                except UserError as error:
                    _logger.warning("Naming stop places stopped: %s", error)
                    return
            stop.place_id = place

    @api.model
    def _refresh(self, date_from, date_to, devices=None):
        if devices is None:
            devices = self.env["device.device"].search([("is_gps_device", "=", True)])
        for timezone, group in devices.grouped(
            lambda device: device._gps_timezone()
        ).items():
            self._refresh_in_timezone(date_from, date_to, group, timezone)

    def _refresh_in_timezone(self, date_from, date_to, devices, timezone):
        date_to = min(date_to, self._local_today(timezone))
        if date_from > date_to or not devices:
            return
        utc_from = self._local_day_start_utc(date_from, timezone)
        utc_to = self._local_day_start_utc(date_to + timedelta(days=1), timezone)
        keep_from = self._earliest_ongoing_arrival(devices, utc_from)
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM device_gps_stop
                 WHERE device_id = ANY(%(ids)s)
                   AND ((kind = 'stop' AND arrival >= %(keep_from)s
                                       AND arrival < %(utc_to)s)
                     OR (kind = 'no_signal' AND date >= %(date_from)s
                                            AND date <= %(date_to)s))
                """,
                ids=devices.ids,
                keep_from=keep_from,
                utc_to=utc_to,
                date_from=date_from,
                date_to=date_to,
            )
        )
        self._insert_stops(devices, keep_from, utc_to, timezone)
        self._insert_no_signal(devices, date_from, date_to, timezone)
        self.invalidate_model()

    def _earliest_ongoing_arrival(self, devices, utc_from):
        self.flush_model()
        self.env.cr.execute(
            SQL(
                """
                SELECT MIN(arrival) FROM device_gps_stop
                 WHERE device_id = ANY(%s) AND kind = 'stop' AND ongoing
                   AND arrival < %s AND arrival >= %s
                """,
                devices.ids,
                utc_from,
                utc_from - ONGOING_MAX_AGE,
            )
        )
        earliest = self.env.cr.fetchone()[0]
        return min(earliest, utc_from) if earliest else utc_from

    def _insert_stops(self, devices, keep_from, utc_to, timezone):
        self.env["device.data.log.gps"].flush_model(
            ["device_id", "speed", "the_point", "timestamp"]
        )
        self.env["resource.gps.binding"].flush_model()
        self.env["resource.resource"].flush_model(["tz"])
        self.env["resource.assignment"].flush_model()
        self.env.cr.execute(
            SQL(
                """
    WITH pos AS (
        SELECT b.binding_id, b.date_end AS binding_end, l.id, l.device_id, l.timestamp, l.the_point,
               COALESCE(l.speed, 0) < %(moving)s AS still
          FROM device_data_log_gps l
          LEFT JOIN LATERAL (%(position_binding)s) b ON TRUE
         WHERE l.device_id = ANY(%(ids)s)
           AND l.timestamp >= %(scan_from)s
           AND l.timestamp < %(utc_to)s
           AND l.the_point IS NOT NULL
    ),
    marked AS (
        SELECT *,
               CASE WHEN NOT still THEN 0
                    WHEN LAG(still) OVER w IS NOT TRUE THEN 1
                    WHEN ST_Distance(the_point::geography,
                                     (LAG(the_point) OVER w)::geography)
                         > %(radius)s THEN 1
                    ELSE 0 END AS starts
          FROM pos
        WINDOW w AS (PARTITION BY device_id, binding_id ORDER BY timestamp, id)
    ),
    grouped AS (
        SELECT *, SUM(starts) OVER (PARTITION BY device_id, binding_id
                                    ORDER BY timestamp, id) AS grp
          FROM marked
    ),
    runs AS (
        SELECT device_id, binding_id, binding_end, grp,
               MIN(timestamp) FILTER (WHERE still) AS arrival,
               MIN(timestamp) FILTER (WHERE NOT still) AS moved_at,
               COUNT(*) FILTER (WHERE still) AS positions,
               (ARRAY_AGG(the_point ORDER BY timestamp, id)
                   FILTER (WHERE still))[1] AS point
          FROM grouped
         WHERE grp > 0
         GROUP BY device_id, binding_id, binding_end, grp
    ),
    stops AS (
        SELECT *,
               COALESCE(moved_at, LEAD(arrival) OVER (PARTITION BY device_id, binding_id
                                                      ORDER BY grp), binding_end) AS departure
          FROM runs
    ),
    kept AS (
        SELECT *,
               EXTRACT(EPOCH FROM (COALESCE(departure, %(now)s) - arrival))
                   / 3600.0 AS duration_hours
          FROM stops
         WHERE arrival >= %(keep_from)s
    )
    INSERT INTO device_gps_stop
        (kind, device_id, asset_id, operator_id, company_id, date,
         arrival, departure, ongoing, duration_hours, positions,
         latitude, longitude, the_point, place_id, geofence_id, partner_id,
         nearby_geofence_id, nearby_distance_m, state_id,
         create_uid, create_date, write_uid, write_date)
    SELECT 'stop', k.device_id, a.id, op.employee_id, COALESCE(binding.company_id, d.company_id),
           (k.arrival AT TIME ZONE 'UTC' AT TIME ZONE COALESCE(binding.tz, device_clock.tz))::date,
           k.arrival, k.departure, k.departure IS NULL, k.duration_hours,
           k.positions, ST_Y(k.point), ST_X(k.point),
           ST_SetSRID(k.point, 4326), known.id,
           here.id, here.partner_id,
           near.id, near.dist, s.state_id,
           %(uid)s, %(now)s, %(uid)s, %(now)s
      FROM kept k
      JOIN device_device d ON d.id = k.device_id
      LEFT JOIN (%(device_timezones)s) device_clock ON device_clock.device_id = d.id
      LEFT JOIN LATERAL (%(arrival_binding)s) binding ON TRUE
      LEFT JOIN resource_resource tracked_resource ON tracked_resource.id = binding.resource_id
      LEFT JOIN resource_resource a ON a.id = tracked_resource.id AND a.kind_id IS NOT NULL
      LEFT JOIN LATERAL %(operator_query)s ON TRUE
      LEFT JOIN LATERAL (
            -- the_geom is Web Mercator; cosd() converts the metres (see
            -- device.device). On nested geofences the innermost wins: a
            -- structure, then a client's parcel, then the property.
            SELECT f.id, f.partner_id
              FROM device_geo_fence f
             WHERE f.active
               AND ST_DWithin(f.the_geom, ST_Transform(k.point, 3857),
                              %(at)s / cosd(ST_Y(k.point)))
             ORDER BY ST_Distance(f.the_geom, ST_Transform(k.point, 3857)),
                      CASE f.area_type WHEN 'structure' THEN 0
                                       WHEN 'parcel' THEN 1 ELSE 2 END,
                      f.partner_id IS NULL
             LIMIT 1
           ) here ON TRUE
      LEFT JOIN LATERAL (
            SELECT f.id,
                   ROUND(ST_Distance(ST_Transform(f.the_geom, 4326)::geography,
                                     k.point::geography))::int AS dist
              FROM device_geo_fence f
             WHERE here.id IS NULL
               AND f.area_type = 'parcel' AND f.active
               AND f.partner_id IS NOT NULL
               AND ST_DWithin(f.the_geom, ST_Transform(k.point, 3857),
                              %(nearby)s / cosd(ST_Y(k.point)))
             ORDER BY ST_Distance(f.the_geom, ST_Transform(k.point, 3857))
             LIMIT 1
           ) near ON TRUE
      LEFT JOIN LATERAL (
            -- A place already named: vehicles park at the same fonda every
            -- day, and the rewrite must not lose what the cron looked up.
            SELECT p.id
              FROM device_gps_place p
             WHERE here.id IS NULL
               AND ST_DWithin(p.the_point::geography, k.point::geography,
                              %(reuse)s)
             ORDER BY p.the_point::geography <-> k.point::geography
             LIMIT 1
           ) known ON TRUE
      LEFT JOIN LATERAL (
            SELECT b.state_id
              FROM device_state_boundary b
             WHERE ST_Contains(b.geom, k.point)
             LIMIT 1
           ) s ON TRUE
     WHERE k.duration_hours * 60 >= %(min_stop)s
                """,
                device_timezones=self.env["device.device"]._gps_timezone_query(),
                position_binding=self.env["resource.gps.binding"]._at_query(
                    SQL("l.device_id"), SQL("l.timestamp")
                ),
                arrival_binding=self.env["resource.gps.binding"]._at_query(
                    SQL("k.device_id"), SQL("k.arrival")
                ),
                operator_query=SQL(
                    live_custody_subquery("operator", "a", "op", at="k.arrival")
                ),
                ids=devices.ids,
                scan_from=keep_from - SCAN_LOOKBACK,
                keep_from=keep_from,
                utc_to=utc_to,
                moving=MOVING_MIN_KMH,
                radius=STOP_RADIUS_M,
                at=AT_GEOFENCE_M,
                nearby=NEARBY_CLIENT_M,
                reuse=PLACE_REUSE_M,
                min_stop=MIN_STOP_MINUTES,
                now=fields.Datetime.now(),
                uid=self.env.uid,
            )
        )

    def _insert_no_signal(self, devices, date_from, date_to, timezone):
        utc_from = self._local_day_start_utc(date_from, timezone)
        utc_to = self._local_day_start_utc(date_to + timedelta(days=1), timezone)
        self.env.cr.execute(
            SQL(
                """
                SELECT device_id,
                       (timestamp AT TIME ZONE 'UTC' AT TIME ZONE %(tz)s)::date,
                       MAX(timestamp)
                  FROM device_data_log_gps
                 WHERE device_id = ANY(%(ids)s)
                   AND timestamp >= %(utc_from)s AND timestamp < %(utc_to)s
                 GROUP BY 1, 2
                """,
                tz=timezone,
                ids=devices.ids,
                utc_from=utc_from,
                utc_to=utc_to,
            )
        )
        last_by_day = defaultdict(dict)
        for device_id, day, last in self.env.cr.fetchall():
            last_by_day[device_id][day] = last
        self.env.cr.execute(
            SQL(
                """
                SELECT device_id, MAX(timestamp)
                  FROM device_data_log_gps
                 WHERE device_id = ANY(%s) AND timestamp < %s
                 GROUP BY device_id
                """,
                devices.ids,
                utc_from,
            )
        )
        seen_before = dict(self.env.cr.fetchall())
        days = [
            date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)
        ]
        vals_list = []
        bindings = self.env["resource.gps.binding"].search(
            [
                ("device_id", "in", devices.ids),
                "|",
                ("date_start", "=", False),
                ("date_start", "<", utc_to),
                "|",
                ("date_end", "=", False),
                ("date_end", ">", utc_from),
            ]
        )
        by_device = bindings.grouped("device_id")
        assignments = (
            self.env["resource.assignment"]
            .sudo()
            .search(
                [
                    ("resource_id", "in", bindings.resource_id.ids),
                    ("custody_role", "=", "operator"),
                    ("date_start", "<", utc_to),
                    "|",
                    ("date_end", "=", False),
                    ("date_end", ">", utc_from),
                ]
            )
        )
        by_resource = assignments.grouped("resource_id")
        employees = {
            employee.resource_id: employee
            for employee in self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            .search([("resource_id", "in", assignments.assignee_id.ids)])
        }
        tz = ZoneInfo(timezone)
        for device in devices:
            last_seen = seen_before.get(device.id)
            created = device.create_date.replace(tzinfo=UTC).astimezone(tz).date()
            for day in days:
                if day in last_by_day[device.id]:
                    last_seen = last_by_day[device.id][day]
                    continue
                if day < created and not last_seen:
                    continue
                at = self._local_day_start_utc(day, timezone) + timedelta(hours=12)
                binding = by_device.get(
                    device, self.env["resource.gps.binding"]
                ).filtered(
                    lambda period, at=at: (
                        (not period.date_start or period.date_start <= at)
                        and (not period.date_end or period.date_end > at)
                    )
                )[:1]
                asset = binding.resource_id.filtered("kind_id")
                holders = (
                    by_resource.get(
                        binding.resource_id, self.env["resource.assignment"]
                    )
                    .filtered(
                        lambda assignment, at=at: (
                            assignment.date_start <= at
                            and (not assignment.date_end or assignment.date_end > at)
                        )
                    )
                    .sorted(
                        lambda assignment: (assignment.date_start, assignment.id),
                        reverse=True,
                    )
                )
                operator = employees.get(holders[:1].assignee_id)
                vals_list.append(
                    {
                        "kind": "no_signal",
                        "device_id": device.id,
                        "asset_id": asset.id,
                        "operator_id": operator.id if operator else False,
                        "company_id": device.company_id.id,
                        "date": day,
                        "last_seen": last_seen,
                    }
                )
        self.create(vals_list)
