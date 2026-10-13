from odoo import fields, models
from odoo.tools import frozendict


class AccountReportBudgetItem(models.Model):
    _name = "account.report.budget.item"
    _access_anchors = frozendict({"company": "budget_id.company_id"})
    _description = "Accounting Report Budget Item"

    budget_id = fields.Many2one(
        comodel_name="account.report.budget",
        index=True,
        required=True,
        ondelete="cascade",
    )
    account_id = fields.Many2one(
        comodel_name="account.account",
        index=True,
        required=True,
        domain="[('account_type', 'in', ('income', 'income_other', 'expense', 'expense_other', 'expense_depreciation', 'expense_direct_cost'))]",
    )
    amount = fields.Float(default=0)
    date = fields.Date(required=True)
