from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrExpenseDecideDuplicate(models.TransientModel):
    _name = "wizard.hr.expense.decide.duplicate"
    _description = "Expense Approve Duplicate"

    expense_ids = fields.Many2many(
        comodel_name="hr.expense",
        readonly=True,
    )
    duplicate_expense_ids = fields.Many2many(
        comodel_name="hr.expense",
        relation="wizard_hr_expense_decide_duplicate_duplicate_rel",
        readonly=True,
    )

    def action_approve(self):
        _debug.pipeline(
            "duplicate_wizard", outcome="approve", expenses=self.expense_ids
        )
        self.expense_ids.filtered(
            lambda expense: expense.state == "submitted"
        )._do_approve()
        return {"type": "ir.actions.act_window_close"}

    def action_refuse(self):
        duplicated = self.expense_ids.filtered(
            lambda expense: (
                expense.state == "submitted"
                and expense._get_duplicate_expenses_to_review()
            )
        )
        _debug.pipeline("duplicate_wizard", outcome="refuse", expenses=duplicated)
        duplicated._do_refuse(self.env._("Duplicate Expense"))
        return {"type": "ir.actions.act_window_close"}
