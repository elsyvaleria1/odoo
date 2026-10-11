from datetime import timedelta

from shapely import wkt
from shapely.geometry import LineString, Point

from odoo import fields, models
from odoo.exceptions import UserError

from .wizard_stock_trip_track_point import TRACK_POINT_COLORS
from odoo.addons.geoengine.models.static_map import (
    MapItem,
    MapStyle,
    render_static_map,
)

CHECKPOINT_KINDS = {
    "departure": "departure",
    "arrival": "arrival",
    "delivery": "delivery",
    "rejection": "not_delivered",
    "not_delivered": "not_delivered",
    "handover": "incident",
    "return": "return",
}
TRACK_MARGIN = timedelta(minutes=5)
ROUTE_MAP_WIDTH = 680
ROUTE_MAP_HEIGHT = 380


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"
    _access_verbs = {
        "view_gps_track": models.Verb(
            requires="read", methods=("action_trip_view_gps_track",)
        ),
    }

    def action_trip_view_gps_track(self):
        self.check_singleton()
        device, start, end = self._trip_track_window()
        Trail = self.env["wizard.device.device.view.trail"].with_privilege(
            "stock_fleet_trace_gps_geoengine.privilege_trip_track",
            reason="a trip draws the GPS track of its vehicle",
        )
        try:
            action = (
                Trail.create(
                    {
                        "selection_mode": "device",
                        "device_ids": device.ids,
                        "date_from": start,
                        "date_to": end,
                        "group_by": "single",
                    }
                )
                .with_context(
                    gps_observation_domain=list(
                        self.vehicle_id.resource_id._gps_observation_domain()
                    )
                )
                .action_generate_trails()
            )
        except UserError as error:
            raise UserError(
                self.env._(
                    "Trip %(trip)s has no GPS track to draw: %(reason)s",
                    trip=self.name,
                    reason=error.args[0] if error.args else "",
                )
            ) from error
        trail = Trail.env["wizard.device.device.view.trail.result"].search(
            action["domain"], limit=1
        )
        trail.write(
            {
                "name": self.env._("Trip %s", self.name),
                "device_id": False,
            }
        )
        Trail.env["wizard.stock.trip.track.point"].create(
            [
                {**vals, "trail_result_id": trail.id}
                for vals in self._trip_track_points()
            ]
        )
        action["name"] = self.env._("GPS track of trip %s", self.name)
        action["context"] = {
            key: value
            for key, value in action.get("context", {}).items()
            if key != "gps_trail_selection_summary"
        }
        return action

    def _trip_track_window(self):
        self.check_singleton()
        device = self.env["device.device"].browse(self.vehicle_id.resource_id._gps_device_ids())
        if not device:
            raise UserError(
                self.env._(
                    "Vehicle %s has no GPS device.", self.vehicle_id.display_name
                )
            )
        if not self.date_departure:
            raise UserError(
                self.env._("Trip %s has not departed: it has no track yet.", self.name)
            )
        start = min(filter(None, [self.trip_gps_exit_date, self.date_departure]))
        end = (
            max(filter(None, [self.trip_gps_entry_date, self.date_return]))
            if self.date_return
            else self.env.cr.now().replace(tzinfo=None)
        )
        return device, start - TRACK_MARGIN, end + TRACK_MARGIN

    def _trip_route_map(self, width=ROUTE_MAP_WIDTH, height=ROUTE_MAP_HEIGHT):
        self.check_singleton()
        items = []
        if self.has_access("view_gps_track"):
            try:
                device, start, end = self._trip_track_window()
            except UserError:
                device = None
            if device:
                logs = self.env["device.data.log.gps"]
                coords, _times = logs.trail_coordinates(
                    logs.with_privilege(
                        "stock_fleet_trace_gps_geoengine.privilege_trip_track",
                        reason="a trip prints its GPS track",
                    ).trail_points(
                        device.ids,
                        start,
                        end,
                        observation_domain=list(
                            self.vehicle_id.resource_id._gps_observation_domain()
                        ),
                    )
                )
                if len(coords) > 1:
                    items.append(
                        MapItem(LineString(coords), 4326, MapStyle(stroke="#ff6a0a"))
                    )
        items.extend(
            MapItem(
                wkt.loads(point["the_point"]),
                4326,
                MapStyle(fill=point["color"], radius=5, stroke=point["color"]),
            )
            for point in self._trip_track_points()
            if point["kind"] != "stop"
        )
        stops = (self.picking_ids | self.trip_checkpoint_ids.picking_id).filtered(
            lambda picking: not picking.trip_support_kind
        )
        for picking in stops.sorted("batch_sequence"):
            location = picking._trip_location()
            if not location:
                continue
            latitude, longitude = location
            items.append(
                MapItem(
                    Point(longitude, latitude),
                    4326,
                    MapStyle(
                        fill=TRACK_POINT_COLORS["stop"],
                        stroke=TRACK_POINT_COLORS["stop"],
                        radius=9,
                        label=str(picking.batch_sequence),
                    ),
                )
            )
        return render_static_map(self.env, items, width=width, height=height)

    def _trip_track_points(self):
        self.check_singleton()
        points = []

        kinds = dict(
            self.env["wizard.stock.trip.track.point"]
            ._fields["kind"]
            ._description_selection(self.env)
        )

        def add(kind, name, date, latitude, longitude):
            if latitude or longitude:
                when = (
                    fields.Datetime.context_timestamp(self, date).strftime(
                        "%Y-%m-%d %H:%M"
                    )
                    if date
                    else ""
                )
                points.append(
                    {
                        "batch_id": self.id,
                        "kind": kind,
                        "name": name,
                        "date": date,
                        "label": " · ".join(filter(None, [kinds[kind], when])),
                        "color": TRACK_POINT_COLORS[kind],
                        "the_point": f"POINT({longitude} {latitude})",
                    }
                )

        stops = self.picking_ids | self.trip_checkpoint_ids.picking_id
        for picking in stops.filtered(lambda p: not p.trip_support_kind):
            latitude, longitude = picking._trip_location() or (0.0, 0.0)
            add(
                "stop",
                f"{picking.name} · {picking.partner_id.display_name or ''}",
                picking.trip_arrival_date,
                latitude,
                longitude,
            )
        labels = dict(
            self.env["stock.trip.checkpoint"]
            ._fields["event_type"]
            ._description_selection(self.env)
        )
        for checkpoint in self.trip_checkpoint_ids:
            kind = CHECKPOINT_KINDS.get(checkpoint.event_type)
            if kind:
                add(
                    kind,
                    " · ".join(
                        filter(
                            None,
                            [labels[checkpoint.event_type], checkpoint.picking_id.name],
                        )
                    ),
                    checkpoint.date,
                    checkpoint.latitude,
                    checkpoint.longitude,
                )
        for incident in self.trip_incident_ids:
            add(
                "incident",
                incident.display_name,
                incident.date,
                incident.latitude,
                incident.longitude,
            )
        alert_labels = dict(
            self.env["stock.trip.alert"]
            ._fields["alert_type"]
            ._description_selection(self.env)
        )
        alerts = self.env["stock.trip.alert"].search([("batch_id", "=", self.id)])
        for alert in alerts:
            add(
                "alert",
                alert_labels[alert.alert_type],
                alert.date,
                alert.latitude,
                alert.longitude,
            )
        return points
