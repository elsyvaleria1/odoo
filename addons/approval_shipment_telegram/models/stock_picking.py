from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    freight_request_ids = fields.Many2many(
        comodel_name="approval.request",
        relation="approval_request_shipment_picking_rel",
        column1="picking_id",
        column2="request_id",
        string="Freight Requests",
        copy=False,
        readonly=True,
    )
