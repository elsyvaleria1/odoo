from odoo import models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def _get_timesheets_and_working_hours_query(self) -> str:
        return """
            SELECT aal.employee_id as employee_id, COALESCE(SUM(aal.unit_amount), 0) as worked_hours
            FROM account_analytic_line aal
            WHERE aal.employee_id = ANY(%s) AND date >= %s AND date <= %s AND aal.holiday_id is NULL AND aal.global_leave_id is NULL
            AND project_id IS NOT NULL
            GROUP BY aal.employee_id
        """
