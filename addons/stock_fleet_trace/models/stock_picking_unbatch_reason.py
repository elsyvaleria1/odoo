from odoo import fields, models


class StockPickingUnbatchReason(models.Model):
    _inherit = "stock.picking.unbatch.reason"

    scope = fields.Selection(
        selection=[
            ("transfer", "Whole delivery"),
            ("line", "Product"),
            ("both", "Whole delivery or product"),
        ],
        default="transfer",
        required=True,
        help="Whether the reason explains a delivery that did not happen, a product "
        "the customer did not take, or either.",
    )
    goods_on_board = fields.Boolean(
        default=True,
        help="The quantity stays on the vehicle and comes back with the unloading. "
        "Clear it for reasons where the goods never travelled, e.g. short loading: "
        "the trip's balance then shows the quantity as missing.",
    )
    creates_backorder = fields.Boolean(
        help="The customer still expects the quantity: what was not delivered stays "
        "pending in a backorder. Otherwise the pending quantity is cancelled.",
    )


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    trip_trace = fields.Boolean(
        string="Trace Load on Vehicle",
        tracking=True,
        help="Trips of this type carry their goods on the vehicle's own location: "
        "they load on departure, need the fuel at departure and return, record what "
        "each customer took and unload what comes back into a reconciled balance.",
    )
