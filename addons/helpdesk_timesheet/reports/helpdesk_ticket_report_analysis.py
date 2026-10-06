from odoo import fields, models
from odoo.tools import frozendict


class HelpdeskTicketReportAnalysis(models.Model):
    _inherit = "helpdesk.ticket.report.analysis"
    _depends = frozendict(
        {
            "helpdesk.ticket": ["total_hours_spent"],
            "hr.employee": ["company_id", "current_version_id", "parent_id", "user_id"],
            "hr.version": ["department_id"],
        }
    )

    total_hours_spent = fields.Float(
        string="Hours Spent (Timesheets)",
        readonly=True,
        aggregator="avg",
        groups="hr_timesheet.group_hr_timesheet_user",
    )
    employee_parent_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Manager",
        readonly=True,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        readonly=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )

    def _select(self):
        select_str = super()._select()
        select_str += """,
            NULLIF(T.total_hours_spent, 0) AS total_hours_spent,
            EMP.parent_id AS employee_parent_id,
            DEP.id AS department_id,
            EMP.id AS employee_id
        """
        return select_str

    def _group_by(self):
        return (
            super()._group_by()
            + """ ,
            DEP.id,
            EMP.parent_id,
            EMP.id,
            T.total_hours_spent
        """
        )

    def _from(self):
        from_str = super()._from()
        from_str += """
            LEFT JOIN res_users U ON T.user_id = U.id
            LEFT JOIN hr_employee EMP ON EMP.user_id = U.id AND ht.company_id = EMP.company_id
            LEFT JOIN hr_version VER ON VER.id = EMP.current_version_id
            LEFT JOIN hr_department DEP ON VER.department_id = DEP.id
        """
        return from_str
