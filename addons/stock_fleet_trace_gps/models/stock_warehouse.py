from odoo import api, fields, models

from odoo.addons.device_gps.tools import haversine_m


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    trip_geofence_radius = fields.Integer(
        string="Geofence Radius (m)",
        default=150,
        help="Around the trips' origin: a delivery vehicle leaving it departs its "
        "trip, entering it returns.",
    )
    trip_stop_radius = fields.Integer(
        string="Customer Radius (m)",
        default=150,
        help="How close to a customer's coordinates the vehicle must stop for the "
        "visit to count.",
    )
    trip_stop_min_minutes = fields.Integer(
        string="Minimum Stop (min)",
        default=3,
        help="How long the vehicle must stay near the customer for the visit to count.",
    )
    trip_unplanned_stop_minutes = fields.Integer(
        string="Unplanned Stop Alert (min)",
        default=10,
        help="A stop this long away from the warehouse and every customer of the "
        "trip raises an alert.",
    )
    trip_gps_silence_minutes = fields.Integer(
        string="GPS Silence Alert (min)",
        default=30,
    )
    has_trip_geofence = fields.Boolean(compute="_compute_has_trip_geofence")

    @api.depends("trip_origin_latitude", "trip_origin_longitude")
    def _compute_has_trip_geofence(self) -> None:
        for warehouse in self:
            warehouse.has_trip_geofence = bool(warehouse._trip_origin_set())

    def _trip_geofence_contains(self, latitude, longitude) -> bool:
        self.check_singleton()
        origin = self._trip_origin_set()
        if not origin:
            return False
        return (
            haversine_m(origin[0], origin[1], latitude, longitude)
            <= self.trip_geofence_radius
        )
