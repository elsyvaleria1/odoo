from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    wallet_reorder_rule_id = fields.Many2one(
        comodel_name="wallet.reorder.rule",
        index="btree_not_null",
        ondelete="set null",
        help="The reordering rule this line tops up.",
    )
    wallet_card_id = fields.Many2one(
        related="wallet_reorder_rule_id.card_id",
    )
