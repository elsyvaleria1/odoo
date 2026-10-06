from collections import defaultdict
from datetime import datetime, timedelta

from odoo import api, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    @api.model
    def _issues_dependencies(self):
        return super()._issues_dependencies() + [
            "employee_id.leave_ids.payslip_state",
            "employee_id.leave_ids.state",
        ]

    def _get_errors_by_slip(self):
        errors_by_slip = super()._get_errors_by_slip()
        slips_by_employee = self.grouped("employee_id")
        leaves_by_slip = defaultdict(lambda: self.env["hr.leave"])
        for leave in self.employee_id.leave_ids.filtered(
            lambda leave: (
                leave.payslip_state == "blocked"
                and leave.state not in ["cancel", "refuse"]
            )
        ):
            for slip in slips_by_employee[leave.employee_id].filtered(
                lambda ps: ps.state == "draft"
            ):
                if (
                    slip.date_from <= leave._get_local_days()[1]
                    and leave._get_local_days()[0] <= slip.date_to
                ):
                    leaves_by_slip[slip] |= leave
        for slip, leaves in leaves_by_slip.items():
            errors_by_slip[slip].append(
                {
                    "message": self.env._("Employee has time off to defer"),
                    "action_text": self.env._("Time Offs"),
                    "action": leaves._get_records_action(),
                    "level": "danger",
                }
            )
        return errors_by_slip

    def compute_sheet(self):
        if self.env.context.get("salary_simulation"):
            return super().compute_sheet()
        regular_payslips = self.filtered(lambda p: p.is_regular)
        if regular_payslips:
            employees = regular_payslips.mapped("employee_id")
            leaves = self.env["hr.leave"].search(
                [
                    ("employee_id", "in", employees.ids),
                    ("state", "not in", ["cancel", "refuse"]),
                ]
            )
            leaves_by_employee = leaves.grouped("employee_id")
            for employee, payslips in regular_payslips.grouped("employee_id").items():
                max_date = datetime.combine(
                    max(payslips.mapped("date_to")) + timedelta(days=1),
                    datetime.min.time(),
                )
                employee_leaves = leaves_by_employee.get(employee, self.env["hr.leave"])
                leaves_to_green = employee_leaves.filtered_domain(
                    [("payslip_state", "!=", "blocked"), ("date_to", "<=", max_date)]
                )
                leaves_to_green.write({"payslip_state": "done"})
        return super().compute_sheet()
