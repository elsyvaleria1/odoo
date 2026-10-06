from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    trip_leg_km = fields.Float(
        string="Leg km (GPS)",
        digits=(16, 1),
        copy=False,
        readonly=True,
        help="Kilometres the vehicle drove from the previous stop, or from the "
        "departure, to this delivery's stop, read from its GPS when the trip "
        "returns. Other deliveries of the same stop show 0.",
    )
