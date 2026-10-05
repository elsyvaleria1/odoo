from odoo import fields, models


class ProductAssetLog(models.Model):
    _inherit = "resource.log"

    source = fields.Selection(
        selection_add=[("approval", "Approval Request")],
        ondelete={"approval": "set default"},
    )

    approval_request_id = fields.Many2one(
        comodel_name="approval.request",
        index="btree_not_null",
        help="Approval request this log entry was booked from.",
    )
