from odoo import fields, models

TRIP_MOVE_KINDS = [
    ("load", "Loading"),
    ("delivery", "Delivery"),
    ("handover", "Handover to another vehicle"),
    ("write_off", "Write-off on the route"),
    ("unload", "Unloading"),
]


class StockMove(models.Model):
    _inherit = "stock.move"

    trip_batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index="btree_not_null",
        help="Trip whose load this move carried onto, along or off the vehicle.",
    )
    trip_move_kind = fields.Selection(
        selection=TRIP_MOVE_KINDS,
        string="Trip Movement",
    )
    trip_target_batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Receiving Trip",
        index="btree_not_null",
        copy=False,
        help="On a handover, the trip of the vehicle that took the goods.",
    )
