import json
import logging
import math
from datetime import UTC, time

from shapely.geometry import Point

from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.datetime import timezone
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

from odoo.addons.device_gps.tools import has_fix, haversine_m
from odoo.addons.geoengine.models.fields import reproject

_logger = logging.getLogger(__name__)

CIRCLE_SEGMENTS = 64

_METERS_PER_DEGREE_LAT = 111320


class DeviceGeofence(models.Model):
    _name = "device.geo.fence"
    _description = "IoT GPS Geofence"
    _order = "name"
    _parent_store = True

    name = fields.Char(
        required=True,
        help="Geofence name",
    )
    active = fields.Boolean(
        default=True,
        help="Whether this geofence is active",
    )
    description = fields.Text(help="Geofence description")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=False,
        help="Company that owns this geofence. Leave empty for multi-company",
    )

    parent_id = fields.Many2one(
        comodel_name="device.geo.fence",
        index=True,
        ondelete="cascade",
        help="Parent geofence for hierarchy (e.g., property containing parcels)",
    )
    child_ids = fields.One2many(
        comodel_name="device.geo.fence",
        inverse_name="parent_id",
        help="Child geofences (e.g., parcels within a property)",
    )
    parent_path = fields.Char(index=True)

    area_type = fields.Selection(
        selection=[
            ("property", "Property"),
            ("parcel", "Parcel"),
            ("structure", "Structure"),
        ],
        default="parcel",
        help="Classification of the geofenced area",
    )

    usage = fields.Selection(
        selection=[
            ("internal", "Internal"),
            ("restricted", "Restricted zone"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
        help="Functional role of this geofence (internal operation, restricted "
        "area, ...). Extended by bridge modules; e.g. agricultural surface.",
    )

    surface = fields.Float(
        digits=(10, 4),
        help="Surface area in hectares",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        help="Contact associated with this geofence",
    )

    state_id = fields.Many2one(
        comodel_name="res.country.state",
        store=True,
        index=True,
        help="State determined from geofence centroid coordinates",
    )
    city = fields.Char(
        store=True,
        help="City/Municipality (optional)",
    )

    geofence_type = fields.Selection(
        selection=[
            ("circle", "Circle"),
            ("polygon", "Polygon"),
            ("rectangle", "Rectangle"),
        ],
        default="polygon",
        required=True,
        help="Geofence shape type",
    )

    center_latitude = fields.Float(
        digits=(10, 7),
        help="Center latitude for circle geofence",
    )
    center_longitude = fields.Float(
        digits=(10, 7),
        help="Center longitude for circle geofence",
    )
    radius = fields.Float(
        default=100.0,
        help="Radius in meters for circle geofence",
    )

    polygon_points = fields.Text(
        compute="_compute_polygon_points",
        inverse="_inverse_polygon_points",
        store=True,
        copy=False,
        readonly=False,
        help="JSON array of [lat, lon] points: the outer ring of the geofence's "
        "first area. Writing it replaces the shape.",
    )
    the_geom = fields.GeoMultiPolygon(
        compute="_compute_the_geom",
        store=True,
        readonly=False,
        help="The geofence's shape: containment and alerts test against it. A "
        "circle's is drawn from its centre and radius.",
    )

    alert_on_enter = fields.Boolean(
        default=True,
        help="Send alert when device enters geofence",
    )
    alert_on_exit = fields.Boolean(
        default=True,
        help="Send alert when device exits geofence",
    )
    alert_on_dwell = fields.Boolean(
        help="Send alert when device stays in geofence too long"
    )
    dwell_time = fields.Integer(
        default=30,
        help="Minutes before dwell alert is triggered",
    )

    schedule_type = fields.Selection(
        selection=[
            ("always", "Always"),
            ("business_hours", "Business Hours"),
            ("custom", "Custom Schedule"),
        ],
        default="always",
        help="When this geofence is active",
    )
    schedule_weekday_ids = fields.Many2many(
        comodel_name="device.weekday",
        relation="device_geo_fence_weekday_rel",
        column1="geo_fence_id",
        column2="weekday_id",
        help="Days when this geofence is active (custom schedule). "
        "Leave empty to activate on all days.",
    )
    schedule_time_from = fields.Float(
        help="Start time (24h format, e.g., 8.5 for 8:30)"
    )
    schedule_time_to = fields.Float(help="End time (24h format, e.g., 17.5 for 17:30)")

    color = fields.Char(
        default="#FF0000",
        help="Color for map display",
    )

    device_ids = fields.Many2many(
        comodel_name="device.device",
        relation="iot_device_geofence_rel",
        column1="geofence_id",
        column2="device_id",
        domain=[("is_gps_device", "=", True)],
        help="Devices monitored by this geofence",
    )
    device_count = fields.Count(
        count_of="device_ids",
        help="Number of devices monitored",
    )

    devices_inside_ids = fields.Many2many(
        comodel_name="device.device",
        relation="iot_device_inside_geofence_rel",
        column1="geofence_id",
        column2="device_id",
        compute="_compute_devices_inside",
        help="Devices currently inside this geofence",
    )
    devices_inside_count = fields.Integer(
        compute="_compute_devices_inside",
        help="Number of devices currently inside",
    )

    devices_inside_last_ids = fields.Many2many(
        comodel_name="device.device",
        relation="iot_device_inside_geofence_last_rel",
        column1="geofence_id",
        column2="device_id",
        help="Devices that were inside this geofence on the previous cron run. "
        "Used to detect enter/exit transitions.",
    )

    @api.constrains(
        "geofence_type",
        "center_latitude",
        "center_longitude",
        "radius",
        "polygon_points",
        "the_geom",
    )
    def _check_geofence_data(self) -> None:
        for geofence in self:
            if geofence.geofence_type == "circle":
                if not has_fix(geofence.center_latitude, geofence.center_longitude):
                    raise ValidationError(
                        self.env._("Circle geofence requires center coordinates"),
                    )
                if geofence.radius <= 0:
                    raise ValidationError(self.env._("Circle radius must be positive"))
                if geofence.radius > 100000:
                    raise ValidationError(
                        self.env._("Circle radius cannot exceed 100km")
                    )
                if abs(geofence.center_latitude) > 90:
                    raise ValidationError(
                        self.env._("Latitude must be between -90 and 90")
                    )
                if abs(geofence.center_longitude) > 180:
                    raise ValidationError(
                        self.env._("Longitude must be between -180 and 180")
                    )
            elif geofence.geofence_type in ["polygon", "rectangle"]:
                if not geofence.polygon_points:
                    raise ValidationError(
                        self.env._("Polygon geofence requires points")
                    )
                try:
                    points = json_loads(geofence.polygon_points)
                    if not isinstance(points, list) or len(points) < 3:
                        raise ValidationError(
                            self.env._("Polygon requires at least 3 points")
                        )
                except json.JSONDecodeError as exc:
                    raise ValidationError(
                        self.env._("Invalid polygon points format")
                    ) from exc
                for point in points:
                    if (
                        not isinstance(point, (list, tuple))
                        or len(point) != 2
                        or any(
                            isinstance(coord, bool)
                            or not isinstance(coord, (int, float))
                            for coord in point
                        )
                    ):
                        raise ValidationError(
                            self.env._(
                                "Each polygon point must be a "
                                "[latitude, longitude] pair of numbers"
                            )
                        )
                    if abs(point[0]) > 90 or abs(point[1]) > 180:
                        raise ValidationError(
                            self.env._(
                                "Polygon point out of range "
                                "(latitude ±90, longitude ±180)"
                            )
                        )

    @api.depends("geofence_type", "center_latitude", "center_longitude", "radius")
    def _compute_the_geom(self) -> None:
        for geofence in self:
            if geofence.geofence_type == "circle":
                geofence.the_geom = geofence._create_circle_polygon() or False
            else:
                geofence.the_geom = geofence.the_geom

    @api.depends("geofence_type", "the_geom")
    def _compute_polygon_points(self) -> None:
        for geofence in self:
            geofence.polygon_points = (
                geofence._get_outer_ring_points()
                if geofence.geofence_type != "circle"
                else False
            )

    def _inverse_polygon_points(self) -> None:
        for geofence in self:
            if geofence.geofence_type != "circle":
                geofence._check_geofence_data()
                geofence.the_geom = geofence._create_polygon_from_points() or False

    def _get_outer_ring_points(self) -> str | bool:
        self.check_singleton()
        if not self.the_geom:
            return False
        shape = reproject(self.the_geom, self._fields["the_geom"].srid, 4326)
        first = shape.geoms[0] if hasattr(shape, "geoms") else shape
        ring = list(first.exterior.coords)[:-1]
        return json_dumps([[round(lat, 7), round(lon, 7)] for lon, lat, *_z in ring])

    def _create_circle_polygon(self) -> str | None:
        self.check_singleton()
        if not self.radius or not has_fix(self.center_latitude, self.center_longitude):
            return None

        lat_rad = math.radians(self.center_latitude)
        meters_per_degree_lon = _METERS_PER_DEGREE_LAT * math.cos(lat_rad)

        radius_lat = self.radius / _METERS_PER_DEGREE_LAT
        radius_lon = self.radius / meters_per_degree_lon

        points = []
        for i in range(CIRCLE_SEGMENTS):
            angle = 2 * math.pi * i / CIRCLE_SEGMENTS
            lon = self.center_longitude + radius_lon * math.cos(angle)
            lat = self.center_latitude + radius_lat * math.sin(angle)
            points.append(f"{lon} {lat}")

        points.append(points[0])

        wkt_ring = ", ".join(points)
        return f"SRID=4326;MULTIPOLYGON((({wkt_ring})))"

    def _create_polygon_from_points(self) -> str | None:
        self.check_singleton()
        if not self.polygon_points:
            return None

        try:
            points = json_loads(self.polygon_points)
            if not points or len(points) < 3:
                return None

            wkt_points = ", ".join([f"{p[1]} {p[0]}" for p in points])
            wkt_points += f", {points[0][1]} {points[0][0]}"
            return f"SRID=4326;MULTIPOLYGON((({wkt_points})))"
        except json.JSONDecodeError, IndexError, TypeError:
            return None

    @api.depends(
        "device_ids",
        "device_ids.log_gps_last_latitude",
        "device_ids.log_gps_last_longitude",
    )
    def _compute_devices_inside(self) -> None:
        for geofence in self:
            inside_devices = self.env["device.device"]
            for device in geofence.device_ids:
                if has_fix(device.log_gps_last_latitude, device.log_gps_last_longitude):
                    if geofence._is_point_inside(
                        device.log_gps_last_latitude,
                        device.log_gps_last_longitude,
                    ):
                        inside_devices |= device
            geofence.devices_inside_ids = inside_devices
            geofence.devices_inside_count = len(inside_devices)

    def _geoengine_map_action(self, domain, name) -> dict:
        return {
            "name": name,
            "type": "ir.actions.act_window",
            "res_model": "device.geo.fence",
            "view_mode": "geoengine",
            "views": [
                (
                    self.env.ref("device_gps_geoengine.view_device_geo_fence_map").id,
                    "geoengine",
                )
            ],
            "domain": domain,
            "target": "current",
        }

    def action_view_on_map(self):
        self.check_singleton()
        return self._geoengine_map_action([("id", "=", self.id)], self.name)

    def action_view_devices(self):
        self.check_singleton()
        return {
            "name": f"Devices - {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "device.device",
            "view_mode": "list,form",
            "domain": [("id", "in", self.device_ids.ids)],
            "context": {
                "default_is_gps_device": True,
            },
        }

    def action_view_devices_inside(self) -> dict:
        self.check_singleton()
        return {
            "name": f"Devices Inside - {self.name}",
            "type": "ir.actions.act_window",
            "res_model": "device.device",
            "view_mode": "list,form,geoengine",
            "domain": [("id", "in", self.devices_inside_ids.ids)],
        }

    def _schedule_local_now(self, now_utc):
        """This geofence's own wall clock at `now_utc`.

        Not the acting user's. The alert loop runs from a cron every five
        minutes, so `self.env.company` is OdooBot's -- company 1, the
        unconfigured placeholder, whose partner carries no timezone at all. The
        `or "UTC"` fallback therefore fired on every single run, and a
        `business_hours` fence over a UTC-6 fleet was live from 02:00 to 12:00
        local instead of 08:00 to 18:00. Nothing raised; the alerts simply came
        at the wrong hours. A schedule is written in the hours of the company
        that owns the fence, so it has to be read back in them.
        """
        self.check_singleton()
        company = self.company_id or self.env.company
        return now_utc.replace(tzinfo=UTC).astimezone(
            timezone(company.partner_id.tz or "UTC")
        )

    def _is_within_schedule(self, now_utc) -> bool:
        """Whether this geofence is watching at `now_utc`.

        Lifted out of the cron loop so the window can be asserted directly. It
        was six hours out for as long as it lived there, and a schedule buried
        inside a batch that also walks devices, computes containment and sends
        alerts is one no test was ever going to pin down on its own.
        """
        self.check_singleton()
        if self.schedule_type == "always":
            return True

        now_local = self._schedule_local_now(now_utc)
        current_time = now_local.time()

        if self.schedule_type == "business_hours":
            return time(8, 0) <= current_time <= time(18, 0) and now_local.weekday() < 5

        if self.schedule_type == "custom":
            if not (self.schedule_time_from and self.schedule_time_to):
                return False
            from_hour = int(self.schedule_time_from)
            from_minute = int((self.schedule_time_from % 1) * 60)
            to_hour = int(self.schedule_time_to)
            to_minute = int((self.schedule_time_to % 1) * 60)
            if not (
                time(from_hour, from_minute) <= current_time <= time(to_hour, to_minute)
            ):
                return False
            active_codes = {wd.code for wd in self.schedule_weekday_ids}
            return not active_codes or str(now_local.weekday()) in active_codes

        return False

    @api.model
    def _cron_process_geofence_alerts(self) -> None:
        _logger.info("Processing geofence alerts")

        now_utc = fields.Datetime.now()
        geofences = self.search([("active", "=", True)])
        pending = []

        for geofence in geofences:
            if not geofence._is_within_schedule(now_utc):
                continue

            devices_was_inside = set(geofence.devices_inside_last_ids.ids)
            current_inside_ids = []

            for device in geofence.device_ids:
                if not has_fix(
                    device.log_gps_last_latitude, device.log_gps_last_longitude
                ):
                    continue

                is_inside = geofence._is_point_inside(
                    device.log_gps_last_latitude,
                    device.log_gps_last_longitude,
                )
                was_inside = device.id in devices_was_inside

                if is_inside:
                    current_inside_ids.append(device.id)

                pending.extend(
                    geofence._prepare_alerts(
                        device, is_inside=is_inside, was_inside=was_inside
                    )
                )

            if set(current_inside_ids) != devices_was_inside:
                geofence.devices_inside_last_ids = [Command.set(current_inside_ids)]

        self._deliver_alerts(pending)
        _logger.info(
            "Geofence alert processing completed: %d alert(s) delivered", len(pending)
        )

    def check_device_position(self, device_id, latitude, longitude):
        self.check_singleton()

        device = self.env["device.device"].browse(device_id)
        if device not in self.device_ids:
            return []

        is_inside = self._is_point_inside(latitude, longitude)
        was_inside = device.id in self.devices_inside_ids.ids

        return self._prepare_alerts(device, is_inside=is_inside, was_inside=was_inside)

    def _deliver_alerts(self, alerts) -> None:
        if not alerts:
            return
        device_model = self.env["device.device"]
        group = self.env.ref("device.group_device_user", raise_if_not_found=False)
        bus = self.env["bus.bus"]

        for alert in alerts:
            device = device_model.browse(alert["device_id"])
            if alert["type"] == "geofence_enter":
                body = self.env._(
                    "Entered geofence %(geofence)s.", geofence=alert["geofence_name"]
                )
            else:
                body = self.env._(
                    "Left geofence %(geofence)s.", geofence=alert["geofence_name"]
                )
            device.message_post(body=body, message_type="notification")
            if group:
                bus._sendone(
                    (group, device.company_id.id or self.env.company.id),
                    "device_device/geofence_alert",
                    {
                        "type": alert["type"],
                        "device_id": alert["device_id"],
                        "device_name": alert["device_name"],
                        "geofence_id": alert["geofence_id"],
                        "geofence_name": alert["geofence_name"],
                    },
                )
            _logger.info(
                "Geofence alert: %s for device %s in %s",
                alert["type"],
                alert["device_name"],
                alert["geofence_name"],
            )

    def _prepare_alerts(self, device, *, is_inside, was_inside):
        self.check_singleton()
        alerts = []

        if is_inside and not was_inside and self.alert_on_enter:
            alerts.append(
                {
                    "type": "geofence_enter",
                    "geofence_id": self.id,
                    "geofence_name": self.name,
                    "device_id": device.id,
                    "device_name": device.name,
                    "timestamp": fields.Datetime.now(),
                },
            )
        elif not is_inside and was_inside and self.alert_on_exit:
            alerts.append(
                {
                    "type": "geofence_exit",
                    "geofence_id": self.id,
                    "geofence_name": self.name,
                    "device_id": device.id,
                    "device_name": device.name,
                    "timestamp": fields.Datetime.now(),
                },
            )

        return alerts

    def _is_point_inside(self, latitude, longitude) -> bool:
        self.check_singleton()
        if self.geofence_type == "circle":
            return self._is_point_inside_circle(latitude, longitude)
        if self.geofence_type in ["polygon", "rectangle"]:
            return self._is_point_inside_shape(latitude, longitude)
        return False

    def _is_point_inside_circle(self, latitude, longitude) -> bool:
        if not has_fix(self.center_latitude, self.center_longitude):
            return False

        distance_m = haversine_m(
            self.center_latitude, self.center_longitude, latitude, longitude
        )
        return distance_m <= self.radius

    def _is_point_inside_shape(self, latitude, longitude) -> bool:
        if not self.the_geom:
            return False
        srid = self._fields["the_geom"].srid
        return self.the_geom.covers(reproject(Point(longitude, latitude), 4326, srid))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._update_surface_from_geom()
        records._update_state_from_coords()
        return records

    def write(self, vals):
        result = super().write(vals)
        geom_fields = {
            "geofence_type",
            "center_latitude",
            "center_longitude",
            "radius",
            "polygon_points",
            "the_geom",
        }
        if geom_fields & set(vals.keys()):
            self._update_surface_from_geom()
            self._update_state_from_coords()
        return result

    def _update_surface_from_geom(self) -> None:
        self.flush_recordset(["the_geom"])
        records = self.filtered(lambda r: r.the_geom)
        if not records:
            return

        self.env.cr.execute(
            """
            UPDATE device_geo_fence
            SET surface = ST_Area(ST_Transform(the_geom, 4326)::geography) / 10000.0
            WHERE id = ANY(%s)
              AND the_geom IS NOT NULL
            """,
            (list(records.ids),),
        )
        if self.env.cr.rowcount:
            records.invalidate_recordset(["surface"])

    def _update_state_from_coords(self) -> None:
        self.flush_recordset(["the_geom"])
        records = self.filtered(lambda r: r.the_geom and not r.state_id)
        if not records:
            return

        self.env.cr.execute(
            """
            UPDATE device_geo_fence
            SET
                center_latitude  = ST_Y(ST_Transform(ST_Centroid(the_geom), 4326)),
                center_longitude = ST_X(ST_Transform(ST_Centroid(the_geom), 4326))
            WHERE id = ANY(%s)
              AND the_geom IS NOT NULL
              AND center_latitude IS NULL
            """,
            (list(records.ids),),
        )

        self.env.cr.execute(
            """
            UPDATE device_geo_fence rgf
            SET state_id = rsb.state_id
            FROM device_state_boundary rsb
            WHERE rgf.id = ANY(%s)
              AND rgf.the_geom IS NOT NULL
              AND rgf.state_id IS NULL
              AND rsb.state_id IS NOT NULL
              AND ST_Contains(
                  rsb.geom,
                  ST_Transform(ST_Centroid(rgf.the_geom), 4326)
              )
            """,
            (list(records.ids),),
        )
        if self.env.cr.rowcount:
            records.invalidate_recordset(
                ["state_id", "center_latitude", "center_longitude"]
            )
