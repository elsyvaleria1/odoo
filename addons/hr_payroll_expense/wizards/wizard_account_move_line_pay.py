from odoo import api, fields, models


class WizardAccountMoveLinePay(models.TransientModel):
    _inherit = "wizard.account.move.line.pay"

    is_already_paid_through_a_payslip = fields.Boolean(
        compute="_compute_is_already_paid_through_a_payslip",
        compute_sudo=True,
    )

    @api.depends("line_ids.move_id")
    def _compute_is_already_paid_through_a_payslip(self) -> None:
        for wizard in self:
            wizard.is_already_paid_through_a_payslip = bool(
                wizard.line_ids.move_id.expense_ids.payslip_id
            )
