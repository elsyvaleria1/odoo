from odoo import fields, models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("autofix", "Autofix")],
        ondelete={"autofix": "cascade"},
    )
