from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    approval_request_line_id = fields.Many2one(
        comodel_name="approval.request.line",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Approval request line this move was created from (creation flow).",
    )
