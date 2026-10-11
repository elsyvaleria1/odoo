import logging
from datetime import UTC, datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CLIENT_PROXIMITY_TOLERANCE_M = 50
DWELL_THRESHOLD_MINUTES = 30
DWELL_STATIONARY_RADIUS_M = 100
DWELL_CLIENT_SEARCH_RADIUS_M = 2000
VISIT_MAX_SILENCE = timedelta(hours=6)
VISIT_LOOKBACK = timedelta(days=2)
DWELL_FALLBACK_USER_LOGIN_PARAM = "device_gps_geoengine.dwell_fallback_user_login"
DWELL_FALLBACK_GROUP = "device_gps_geoengine.group_device_gps_geofence_editor"
ADDRESS_KEY_DECIMALS = 4
ADDRESS_PARTS = (
    ("road",),
    ("neighbourhood", "suburb", "quarter", "hamlet", "village"),
    ("town", "city", "municipality", "county"),
    ("state",),
)


class DeviceDevice(models.Model):
    _inherit = "device.device"
    _access_verbs = {
        "locate": models.Verb(requires="read", methods=("get_current_address",)),
    }

    the_point = fields.GeoPoint(
        related="log_gps_last_id.the_point",
        string="GPS Location",
        help="Current device location for map display",
    )

    current_client_geofence_id = fields.Many2one(
        comodel_name="device.geo.fence",
        string="Current Client Parcel",
        compute="_compute_current_client_geofence",
        help="Client parcel geofence closest to the device's last known "
        f"position, within {CLIENT_PROXIMITY_TOLERANCE_M} m",
    )
    current_client_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Current Client",
        compute="_compute_current_client_geofence",
    )
    current_client_distance_m = fields.Integer(
        string="Distance to Parcel (m)",
        compute="_compute_current_client_geofence",
        help="Geodesic metres from the last known position to the edge of "
        "current_client_geofence_id: 0 while inside the polygon, up to the "
        "proximity tolerance while beside it.",
    )

    current_address = fields.Char(
        string="Current Address",
        readonly=True,
        help="Street address of the last GPS position, reverse-geocoded when "
        "the live map's popup asks for it. A cache: current_address_key says "
        "which position it describes.",
    )
    current_address_key = fields.Char(
        readonly=True,
        help="The position current_address was resolved for, rounded to "
        f"{ADDRESS_KEY_DECIMALS} decimals. A vehicle standing still keeps its "
        "key, so reopening its popup costs no request.",
    )

    gps_speed_avg_today = fields.Float(
        string="Average Speed Today (km/h)",
        digits=(6, 0),
        compute="_compute_gps_speed_today",
        help="Mean of today's speed readings while moving (zero readings "
        "excluded), in the user's timezone. Per reading, not per time: a "
        "tracker that reports more often on the highway pulls it up.",
    )
    gps_speed_max_today = fields.Float(
        string="Maximum Speed Today (km/h)",
        digits=(6, 0),
        compute="_compute_gps_speed_today",
    )

    def _compute_gps_speed_today(self) -> None:
        by_device = self._gps_speed_today_by_device()
        for device in self:
            avg, top = by_device.get(device.id, (0.0, 0.0))
            device.gps_speed_avg_today = avg
            device.gps_speed_max_today = top

    def _gps_speed_today_by_device(self) -> dict:
        if not self.ids:
            return {}
        tz = self.env.tz
        local_day = datetime.now(tz).date()
        day_start = (
            datetime.combine(local_day, time.min, tzinfo=tz)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        self.env["device.data.log.gps"].flush_model(["device_id", "timestamp", "speed"])
        self.env.cr.execute(
            """
            SELECT device_id,
                   COALESCE(AVG(NULLIF(speed, 0)), 0),
                   COALESCE(MAX(speed), 0)
              FROM device_data_log_gps
             WHERE device_id = ANY(%s)
               AND timestamp >= %s
             GROUP BY device_id
            """,
            (self.ids, day_start),
        )
        return {
            device_id: (round(avg), round(top))
            for device_id, avg, top in self.env.cr.fetchall()
        }

    def get_current_address(self) -> str | bool:
        self.check_singleton()
        latitude = self.log_gps_last_latitude
        longitude = self.log_gps_last_longitude
        if not (latitude or longitude):
            return False
        key = (
            f"{latitude:.{ADDRESS_KEY_DECIMALS}f},{longitude:.{ADDRESS_KEY_DECIMALS}f}"
        )
        if self.current_address_key != key:
            address = self._reverse_geocode(latitude, longitude)
            if not address:
                return False
            self.with_privilege(
                "device_gps_geoengine.privilege_cache_current_address",
                reason="cache the address of the device's last position",
            ).write({"current_address": address, "current_address_key": key})
        return self.current_address

    def _reverse_geocode(self, latitude: float, longitude: float) -> str | bool:
        try:
            result = self.env["geocoder"]._call_openstreetmap_reverse(
                latitude, longitude
            )
        except UserError as error:
            _logger.warning(
                "No address for %s at %s,%s: %s",
                self.display_name,
                latitude,
                longitude,
                error,
            )
            return False
        parts = (result or {}).get("address") or {}
        names = []
        for group in ADDRESS_PARTS:
            name = next((parts[k] for k in group if parts.get(k)), None)
            if name and name not in names:
                names.append(name)
        return ", ".join(names) or (result or {}).get("display_name") or False

    def _compute_map_labels(self) -> None:
        for device in self:
            device.map_title = device.name
            device.map_subtitle = False

    @api.depends("the_point")
    def _compute_current_client_geofence(self) -> None:
        by_device = self._nearest_client_geofence_by_device()
        for device in self:
            geofence, distance = by_device.get(
                device.id, (self.env["device.geo.fence"], 0)
            )
            device.current_client_geofence_id = geofence
            device.current_client_partner_id = geofence.partner_id
            device.current_client_distance_m = distance

    def _nearest_client_geofence_by_device(self) -> dict:
        device_ids = [device.id for device in self if device.log_gps_last_id]
        if not device_ids:
            return {}
        self.env["device.geo.fence"].flush_model(
            ["active", "area_type", "partner_id", "the_geom", "company_id"]
        )
        self.env["device.data.log.gps"].flush_model(["the_point"])
        self.flush_recordset(["log_gps_last_id", "company_id"])
        self.env.cr.execute(
            """
            SELECT DISTINCT ON (d.id) d.id, f.id,
                   -- True metres for display, computed only for the few
                   -- rows the indexed ST_DWithin below let through.
                   ST_Distance(ST_Transform(f.the_geom, 4326)::geography,
                               l.the_point::geography)
              FROM device_device d
              JOIN device_data_log_gps l ON l.id = d.log_gps_last_id
              JOIN device_geo_fence f
                ON f.area_type = 'parcel'
               AND (f.company_id IS NULL OR f.company_id = d.company_id)
               AND f.active
               AND f.partner_id IS NOT NULL
               AND ST_DWithin(
                     f.the_geom,
                     ST_Transform(l.the_point, 3857),
                     -- the_geom is Web Mercator, which inflates every distance
                     -- by 1/cos(latitude); dividing converts the tolerance from
                     -- metres into the projection's own units, so 50 m means
                     -- 50 m in Chiapas and at the northern border alike. Left
                     -- uncorrected it meant 48.4 m and 42.1 m respectively.
                     -- Casting both sides to geography is also correct and
                     -- costs the GiST index on the_geom: measured over 5,000
                     -- parcels, 0.18 ms index scan becomes a 239 ms seq scan.
                     %s / cosd(ST_Y(l.the_point))
                 )
             WHERE d.id = ANY(%s)
             -- Ordering needs no such correction: the factor depends only on
             -- the device's own latitude, so it is constant within each
             -- DISTINCT ON group and cannot reorder it.
             ORDER BY d.id, ST_Distance(f.the_geom, ST_Transform(l.the_point, 3857))
            """,
            (CLIENT_PROXIMITY_TOLERANCE_M, device_ids),
        )
        geofence_model = self.env["device.geo.fence"]
        return {
            device_id: (geofence_model.browse(geofence_id), round(distance))
            for device_id, geofence_id, distance in self.env.cr.fetchall()
        }

    map_title = fields.Char(
        compute="_compute_map_labels",
        help="Headline the live map puts on this device's marker. The map does "
        "not know what a vehicle or a driver is; a bridge that does overrides "
        "this to say so.",
    )
    map_subtitle = fields.Char(compute="_compute_map_labels")

    gps_geofence_ids = fields.Many2many(
        comodel_name="device.geo.fence",
        relation="iot_device_geofence_rel",
        column1="device_id",
        column2="geofence_id",
        string="Monitored Geofences",
        help="Geofences being monitored for this device",
    )
    gps_inside_geofence_ids = fields.Many2many(
        comodel_name="device.geo.fence",
        relation="iot_device_inside_geofence_rel",
        column1="device_id",
        column2="geofence_id",
        string="Inside Geofences",
        compute="_compute_inside_geofences",
        help="Geofences the device is currently inside",
    )

    @api.depends("log_gps_last_latitude", "log_gps_last_longitude", "gps_geofence_ids")
    def _compute_inside_geofences(self) -> None:
        for device in self:
            inside = self.env["device.geo.fence"]
            if device.log_gps_last_latitude and device.log_gps_last_longitude:
                for geofence in device.gps_geofence_ids:
                    if geofence._is_point_inside(
                        device.log_gps_last_latitude,
                        device.log_gps_last_longitude,
                    ):
                        inside |= geofence
            device.gps_inside_geofence_ids = inside

    def write(self, vals):
        res = super().write(vals)
        if vals.get("log_gps_last_id"):
            self._broadcast_gps_positions()
        return res

    def _notify_gps_pointer_moved(self):
        super()._notify_gps_pointer_moved()
        self._broadcast_gps_positions()

    def _broadcast_gps_positions(self) -> None:
        bus = self.env["bus.bus"]
        group = self.env.ref("device.group_device_user", raise_if_not_found=False)
        if not group:
            return
        for device in self:
            gps_log = device.log_gps_last_id
            if not gps_log:
                continue
            company = device.company_id or self.env.company
            bus._sendone(
                (group, company.id),
                "device_device/gps_position",
                {
                    "device_id": device.id,
                    "latitude": gps_log.latitude,
                    "longitude": gps_log.longitude,
                    "speed": gps_log.speed,
                    "timestamp": (
                        gps_log.timestamp.isoformat() if gps_log.timestamp else False
                    ),
                },
            )

    dwell_notification_sent = fields.Boolean(
        help="A mapping request has already been raised for the current "
        "unmapped stop. Reset once the device moves on or lands on a "
        "mapped parcel, so the next unmapped stop notifies again."
    )

    @api.model
    def _cron_check_unmapped_dwell(self) -> None:
        devices = self.search([("is_gps_device", "=", True), ("active", "=", True)])
        for device in devices:
            dwelling = device._is_unmapped_dwell()
            if dwelling and not device.dwell_notification_sent:
                device._notify_unmapped_dwell()
                device.dwell_notification_sent = True
            elif not dwelling and device.dwell_notification_sent:
                device.dwell_notification_sent = False

    def _is_unmapped_dwell(self) -> bool:
        self.check_singleton()
        if self.current_client_geofence_id:
            return False

        last_log = self.log_gps_last_id
        if not last_log or not last_log.the_point:
            return False

        cutoff = fields.Datetime.now() - timedelta(minutes=DWELL_THRESHOLD_MINUTES)
        older_log = self.env["device.data.log.gps"].search(
            [
                ("device_id", "=", self.id),
                ("timestamp", "<=", cutoff),
                ("the_point", "!=", False),
            ],
            order="timestamp desc",
            limit=1,
        )
        if not older_log:
            return False

        self.env.cr.execute(
            """
            SELECT max(ST_Distance(
                the_point::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            ))
              FROM device_data_log_gps
             WHERE device_id = %s AND timestamp >= %s AND the_point IS NOT NULL
            """,
            (last_log.longitude, last_log.latitude, self.id, cutoff),
        )
        (max_distance,) = self.env.cr.fetchone()
        return max_distance is not None and max_distance <= DWELL_STATIONARY_RADIUS_M

    def _notify_unmapped_dwell(self) -> None:
        self.check_singleton()
        partner = self._find_nearby_unmapped_client()
        recipient = partner.user_id if partner else self.env["res.users"]
        if not recipient:
            recipient = self._dwell_fallback_user()
        if not recipient:
            _logger.warning(
                "%s has been stationary off any mapped parcel, and there is "
                "nobody to tell: no nearby client has a salesperson, %s names "
                "no user, and %s is empty. The mapping request is dropped.",
                self.display_name,
                DWELL_FALLBACK_USER_LOGIN_PARAM,
                DWELL_FALLBACK_GROUP,
            )
            return

        summary = self.env._("Vehicle stopped without a mapped client parcel")
        note = self.env._(
            "%(device)s has been stationary for %(minutes)s+ minutes at a "
            "location not linked to any mapped client parcel.%(near)s Please "
            "map the exact parcel in Remote so future stops resolve "
            "automatically.",
            device=self.display_name,
            minutes=DWELL_THRESHOLD_MINUTES,
            near=(
                self.env._(
                    " Nearest known client: %(partner)s.",
                    partner=partner.display_name,
                )
                if partner
                else ""
            ),
        )
        target = partner or self
        target.activity_schedule(
            "mail.mail_activity_data_todo",
            summary=summary,
            note=note,
            user_id=recipient.id,
        )

    def _find_nearby_unmapped_client(self):
        self.check_singleton()
        last_log = self.log_gps_last_id
        self.env.cr.execute(
            """
            SELECT id
              FROM res_partner
             WHERE (partner_latitude != 0 OR partner_longitude != 0)
               AND ST_DWithin(
                   ST_SetSRID(
                       ST_MakePoint(partner_longitude, partner_latitude), 4326
                   )::geography,
                   ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
                   %(radius)s
               )
             ORDER BY ST_Distance(
                 ST_SetSRID(
                     ST_MakePoint(partner_longitude, partner_latitude), 4326
                 )::geography,
                 ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography
             )
             LIMIT 1
            """,
            {
                "lon": last_log.longitude,
                "lat": last_log.latitude,
                "radius": DWELL_CLIENT_SEARCH_RADIUS_M,
            },
        )
        row = self.env.cr.fetchone()
        return (
            self.env["res.partner"].browse(row[0]) if row else self.env["res.partner"]
        )

    def _dwell_fallback_user(self):
        login = self.env.registry.settings.get(
            self.env, DWELL_FALLBACK_USER_LOGIN_PARAM, default=False
        )
        if login:
            user = self.env["res.users"].search([("login", "=", login)], limit=1)
            if user:
                return user
            _logger.warning(
                "%s names login %r, which no user has; falling back to %s",
                DWELL_FALLBACK_USER_LOGIN_PARAM,
                login,
                DWELL_FALLBACK_GROUP,
            )
        editors = self.env.ref(DWELL_FALLBACK_GROUP).sudo().all_user_ids
        return editors.sorted("id")[:1]

    client_visit_geofence_id = fields.Many2one(
        comodel_name="device.geo.fence",
        string="Visited Parcel",
        help="Parcel of the current or most recent client visit. Kept after "
        "the device leaves (client_visit_departure gets set) until a new "
        "visit -- to this or another parcel -- starts.",
    )
    client_visit_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Visited Client",
    )
    client_visit_arrival = fields.Datetime(
        string="Arrival Time",
        help="When the device was first detected on client_visit_geofence_id.",
    )
    client_visit_departure = fields.Datetime(
        string="Departure Time",
        help="When the device was first detected off client_visit_geofence_id. "
        "Empty while the visit is still ongoing.",
    )
    client_visit_log_id = fields.Many2one(
        comodel_name="device.client.visit",
        string="Open Visit Log",
        help="The device.client.visit row for the current visit, open "
        "(no departure) until the device leaves.",
    )

    @api.model
    def _cron_track_client_visits(self) -> None:
        now = fields.Datetime.now()
        devices = self.search([("is_gps_device", "=", True), ("active", "=", True)])
        for device in devices:
            device._track_client_visit(now)

    def _track_client_visit(self, now) -> None:
        self.check_singleton()
        current = self.current_client_geofence_id
        ongoing = self._ongoing_client_visit_geofence()
        last_log = self.log_gps_last_id
        last_seen = (last_log.timestamp if last_log else None) or now
        if current == ongoing:
            if ongoing and now - last_seen > VISIT_MAX_SILENCE:
                self._close_client_visit(last_seen)
            return
        if ongoing:
            self._close_client_visit(last_seen)
        if current:
            arrival = self._find_visit_arrival(current)
            if not self._stay_was_already_closed(current, arrival, now, last_seen):
                self._open_client_visit(current, arrival)

    def _stay_was_already_closed(self, geofence, arrival, now, last_seen) -> bool:
        return bool(
            now - last_seen > VISIT_MAX_SILENCE
            and self.client_visit_departure
            and self.client_visit_geofence_id == geofence
            and arrival <= self.client_visit_departure
        )

    def _ongoing_client_visit_geofence(self):
        if self.client_visit_departure:
            return self.env["device.geo.fence"]
        return self.client_visit_geofence_id

    def _close_client_visit(self, departure) -> None:
        if self.client_visit_arrival:
            departure = max(departure, self.client_visit_arrival)
        self.client_visit_departure = departure
        if self.client_visit_log_id and not self.client_visit_log_id.departure:
            self.client_visit_log_id.departure = departure

    def _open_client_visit(self, geofence, arrival) -> None:
        visit = self.env["device.client.visit"].create(
            {
                "device_id": self.id,
                "partner_id": geofence.partner_id.id,
                "geofence_id": geofence.id,
                "arrival": arrival,
            }
        )
        self.write(
            {
                "client_visit_geofence_id": geofence.id,
                "client_visit_partner_id": geofence.partner_id.id,
                "client_visit_arrival": arrival,
                "client_visit_departure": False,
                "client_visit_log_id": visit.id,
            }
        )

    def _find_visit_arrival(self, geofence):
        self.check_singleton()
        last_log = self.log_gps_last_id
        if not last_log or not last_log.timestamp:
            return fields.Datetime.now()
        self.env["device.data.log.gps"].flush_model(["the_point", "timestamp"])
        self.env.cr.execute(
            """
            WITH recent AS (
                SELECT l.timestamp,
                       ST_DWithin(
                           f.the_geom, ST_Transform(l.the_point, 3857),
                           %(tolerance)s / cosd(ST_Y(l.the_point))
                       ) AS on_parcel
                  FROM device_data_log_gps l
                  JOIN device_geo_fence f ON f.id = %(geofence_id)s
                 WHERE l.device_id = %(device_id)s
                   AND l.the_point IS NOT NULL
                   AND l.timestamp <= %(until)s
                   AND l.timestamp >= %(since)s
                 ORDER BY l.timestamp DESC, l.id DESC
                 LIMIT 5000
            ),
            walked AS (
                SELECT timestamp, on_parcel,
                       LEAD(timestamp) OVER (ORDER BY timestamp DESC) AS prev_ts
                  FROM recent
            ),
            boundary AS (
                SELECT timestamp, on_parcel
                  FROM walked
                 WHERE NOT on_parcel
                    OR prev_ts IS NULL
                    OR timestamp - prev_ts > %(max_silence)s
                 ORDER BY timestamp DESC
                 LIMIT 1
            )
            SELECT MIN(w.timestamp)
              FROM walked w, boundary b
             WHERE w.on_parcel
               AND w.timestamp >= b.timestamp
            """,
            {
                "tolerance": CLIENT_PROXIMITY_TOLERANCE_M,
                "geofence_id": geofence.id,
                "device_id": self.id,
                "until": last_log.timestamp,
                "since": last_log.timestamp - VISIT_LOOKBACK,
                "max_silence": VISIT_MAX_SILENCE,
            },
        )
        (arrival,) = self.env.cr.fetchone()
        return arrival or last_log.timestamp

    def action_view_today_trail(self):
        self.check_singleton()

        trail_wizard = self.env["wizard.device.device.view.trail"]
        wizard = trail_wizard.create(
            {
                "selection_mode": "device",
                "device_ids": [fields.Command.set([self.id])],
            }
        )

        return wizard.action_generate_trails()
