from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    trip_gps_arrival = fields.Datetime(
        string="Arrival (GPS)",
        copy=False,
        readonly=True,
        help="When the vehicle's track first stayed at the customer's location.",
    )
    trip_gps_departure = fields.Datetime(
        string="Left Customer (GPS)",
        copy=False,
        readonly=True,
    )
    trip_gps_verified = fields.Boolean(
        string="Visit Verified by GPS",
        copy=False,
        readonly=True,
    )
