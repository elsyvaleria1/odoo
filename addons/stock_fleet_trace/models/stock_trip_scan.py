from odoo import fields, models


class StockTripScan(models.Model):
    _name = "stock.trip.scan"
    _description = "Trip Scan"
    _order = "date desc, id desc"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        string="Trip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="batch_id.company_id",
    )
    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Delivery",
        index="btree_not_null",
    )
    code = fields.Char(required=True)
    kind = fields.Selection(
        selection=[
            ("trip_sheet", "Trip sheet"),
            ("delivery", "Delivery slip"),
            ("lot", "Product lot"),
        ],
        required=True,
    )
    product_id = fields.Many2one(comodel_name="product.product")
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot",
    )
    quantity = fields.Float(
        digits="Product Unit",
        default=1.0,
    )
    date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Scanned By",
        default=lambda self: self.env.user,
        required=True,
    )


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    trip_scan_ids = fields.One2many(
        comodel_name="stock.trip.scan",
        inverse_name="batch_id",
        string="Scans",
    )
