from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    trace_id = fields.Many2one(
        related="asset_id.trace_id",
        store=True,
        index="btree_not_null",
    )
