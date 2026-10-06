from odoo import fields, models


class ResourceAssetVehicle(models.Model):
    _inherit = "resource.asset.vehicle"

    trip_delivery_vehicle = fields.Boolean(
        string="Delivery Vehicle",
        help="Leaving a warehouse geofence without a loaded trip raises an alert. "
        "Leave it clear for vehicles that go out for other reasons, e.g. agronomists'.",
    )
    trip_gps_cursor = fields.Datetime(
        string="GPS Read Up To",
        copy=False,
        readonly=True,
        help="Timestamp of the last GPS reading the trips have processed.",
    )
    trip_gps_inside_warehouse_id = fields.Many2one(
        comodel_name="stock.warehouse",
        string="Inside Warehouse (GPS)",
        copy=False,
        readonly=True,
        help="Warehouse geofence the last processed reading was inside.",
    )
