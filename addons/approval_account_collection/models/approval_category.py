from odoo import fields, models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("collection_hand_in", "Cash Hand-in")],
        ondelete={"collection_hand_in": "cascade"},
    )
