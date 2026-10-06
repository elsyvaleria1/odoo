from odoo import api, fields, models

from odoo.addons.geoengine.models.fields import geodesic_length_km


class WizardDeviceDeviceViewTrailResult(models.TransientModel):
    _name = "wizard.device.device.view.trail.result"
    _description = "GPS Trail Result"
    _rec_name = "name"

    name = fields.Char(required=True)
    the_trail = fields.GeoLine(
        srid=4326,
        help="Geographic line representing the trail (WGS84/EPSG:4326)",
    )

    device_id = fields.Many2one(
        comodel_name="device.device",
        help="Source GPS device for this trail",
    )
    device_name = fields.Char(compute="_compute_display_fields")

    point_count = fields.Integer(help="Number of GPS points in this trail")
    date_from = fields.Datetime()
    date_to = fields.Datetime()
    trail_color = fields.Char(default="#3366FF")
    trail_timestamps = fields.Text(
        help="JSON array of Unix timestamps (seconds) for each coordinate in the trail. "
        "Used for WebGL time-based animation."
    )
    length_km = fields.Float(
        digits=(12, 2),
        compute="_compute_length_km",
        help="Approximate trail length in kilometers",
    )

    duration_hours = fields.Float(
        digits=(10, 2),
        help="Total time span from first to last GPS point",
    )
    driving_hours = fields.Float(
        digits=(10, 2),
        help="Time with ignition ON and vehicle moving",
    )
    idling_hours = fields.Float(
        digits=(10, 2),
        help="Time with ignition ON but vehicle stationary",
    )
    parked_hours = fields.Float(
        digits=(10, 2),
        help="Time with ignition OFF",
    )

    distance_gps = fields.Float(
        digits=(12, 2),
        help="Distance calculated from GPS coordinates (Haversine)",
    )
    distance_odo = fields.Float(
        digits=(12, 2),
        help="Distance from odometer readings (end - start)",
    )
    odometer_start = fields.Float(
        digits=(12, 2),
        help="Odometer reading at trail start",
    )
    odometer_end = fields.Float(
        digits=(12, 2),
        help="Odometer reading at trail end",
    )

    speed_avg = fields.Float(
        digits=(10, 1),
        help="Average speed while moving (excludes stationary points)",
    )
    speed_max = fields.Float(
        digits=(10, 1),
        help="Maximum speed recorded during trail",
    )

    fuel_consumed = fields.Float(
        digits=(10, 2),
        help="Fuel consumed during trail",
    )
    fuel_efficiency = fields.Float(
        digits=(10, 2),
        compute="_compute_fuel_efficiency",
        help="Kilometers per liter (higher is better)",
    )
    fuel_start = fields.Float(
        digits=(5, 1),
        help="Fuel level at trail start",
    )
    fuel_end = fields.Float(
        digits=(5, 1),
        help="Fuel level at trail end",
    )

    stop_count = fields.Integer(help="Number of ignition-off stops during trail")

    @api.depends("device_id")
    def _compute_display_fields(self) -> None:
        for result in self:
            result.device_name = result.device_id.name if result.device_id else ""

    @api.depends("the_trail")
    def _compute_length_km(self) -> None:
        for result in self:
            result.length_km = geodesic_length_km(result.the_trail)

    @api.depends("distance_odo", "distance_gps", "fuel_consumed")
    def _compute_fuel_efficiency(self) -> None:
        for result in self:
            if result.fuel_consumed and result.fuel_consumed > 0:
                distance = result.distance_odo or result.distance_gps or 0
                result.fuel_efficiency = distance / result.fuel_consumed
            else:
                result.fuel_efficiency = 0.0
