from odoo import fields, models
from odoo.tools import format_date


class WizardAccountLoanClose(models.TransientModel):
    _name = "wizard.account.loan.close"
    _description = "Close Loan Wizard"

    loan_id = fields.Many2one(
        comodel_name="account.loan",
        required=True,
    )
    date = fields.Date(
        string="Close Date",
        default=fields.Date.context_today,
        required=True,
    )

    def action_save(self):
        self.check_singleton()
        self.loan_id.line_ids.generated_move_ids.filtered(
            lambda move: (
                move.state == "draft" and move.generating_loan_line_id.date > self.date
            )
        ).unlink()
        self.loan_id._set_state("closed")
        self.loan_id.message_post(
            body=self.env._(
                "Closed on the %(date)s", date=format_date(self.env, self.date)
            )
        )
        return {"type": "ir.actions.act_window_close"}
