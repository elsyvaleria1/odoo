from odoo import api, fields, models


class WizardHrExpenseRefuse(models.TransientModel):
    _name = "wizard.hr.expense.refuse"
    _description = "Expense Refuse Reason Wizard"

    reason = fields.Char(required=True)
    expense_ids = fields.Many2many(comodel_name="hr.expense")

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if "expense_ids" in fields:
            res["expense_ids"] = self.env.context.get("active_ids", [])
        return res

    def action_refuse(self):
        self.expense_ids._do_refuse(self.reason)
        return {"type": "ir.actions.act_window_close"}
