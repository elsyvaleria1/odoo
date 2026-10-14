from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    fleet_exit = fields.Boolean(
        string="Vehicle Routes",
        help="Its trips carry route activities instead of transfers and leave once "
        "a vehicle exit authoriser authorises them.",
    )
