from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"

    def _prepare_analytic_line_values(self, account, amount, unit_amount):
        self.check_singleton()
        res = self.workorder_id._prepare_analytic_line_values(
            account, amount, unit_amount
        )
        res["name"] = self.env._(
            "[EMPL] %(work_order)s - %(employee)s",
            work_order=self.workorder_id.display_name,
            employee=self.employee_id.name,
        )
        res["employee_id"] = self.employee_id.id
        return res


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    employee_analytic_account_line_ids = fields.Many2many(
        comodel_name="account.analytic.line",
        copy=False,
    )

    def action_cancel(self):
        _debug.lifecycle(
            "employee_analytic_lines_dropped",
            workorders=self,
            lines=len(self.employee_analytic_account_line_ids),
        )
        self.employee_analytic_account_line_ids.unlink()
        return super().action_cancel()
