from odoo import api, fields, models


class StockTripBalance(models.Model):

    _name = "stock.trip.balance"
    _description = "Trip Balance Line"
    _order = "batch_id, product_id, trace_id"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
    )
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot",
    )
    uom_id = fields.Many2one(related="product_id.uom_id")
    qty_loaded = fields.Float(
        string="Loaded",
        digits="Product Unit",
    )
    qty_received = fields.Float(
        string="Received",
        digits="Product Unit",
        help="Taken over from another vehicle.",
    )
    qty_delivered = fields.Float(
        string="Delivered",
        digits="Product Unit",
    )
    qty_written_off = fields.Float(
        string="Written Off",
        digits="Product Unit",
    )
    qty_handed_over = fields.Float(
        string="Handed Over",
        digits="Product Unit",
        help="Given to another vehicle.",
    )
    qty_expected = fields.Float(
        string="Expected Back",
        digits="Product Unit",
        compute="_compute_qty_expected",
        store=True,
    )
    qty_returned = fields.Float(
        string="Unloaded",
        digits="Product Unit",
    )
    qty_difference = fields.Float(
        string="Difference",
        digits="Product Unit",
        compute="_compute_qty_expected",
        store=True,
        help="Unloaded minus expected: negative is missing, positive is surplus. "
        "Only meaningful once the unloading is confirmed.",
    )

    @api.depends(
        "qty_loaded",
        "qty_received",
        "qty_delivered",
        "qty_written_off",
        "qty_handed_over",
        "qty_returned",
    )
    def _compute_qty_expected(self) -> None:
        for line in self:
            line.qty_expected = (
                line.qty_loaded
                + line.qty_received
                - line.qty_delivered
                - line.qty_written_off
                - line.qty_handed_over
            )
            line.qty_difference = line.qty_returned - line.qty_expected
