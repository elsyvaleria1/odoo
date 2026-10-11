from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    trace_id = fields.Many2one(  # noqa: E8529 -- One2many inverse of stock.lot.account_move_line_ids
        related="asset_id.trace_id",
        store=True,
        index="btree_not_null",
    )
