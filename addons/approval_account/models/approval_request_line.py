from odoo import fields, models


class ApprovalRequestLine(models.Model):
    _inherit = "approval.request.line"

    account_move_line_id = fields.Many2one(
        comodel_name="account.move.line",
        index=True,
        copy=False,
        readonly=True,
        help="Link to the account move line created from this approval line",
    )
    account_move_id = fields.Many2one(
        comodel_name="account.move",
        related="account_move_line_id.move_id",
        readonly=True,
        help="Account move that contains the line created from this approval",
    )

    def _get_fields_line_system(self) -> frozenset[str]:
        return super()._get_fields_line_system() | {"account_move_line_id"}
