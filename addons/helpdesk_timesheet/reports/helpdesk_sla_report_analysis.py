from odoo import fields, models
from odoo.tools import frozendict


class HelpdeskSlaReportAnalysis(models.Model):
    _inherit = "helpdesk.sla.report.analysis"
    _depends = frozendict(
        {
            "helpdesk.ticket": ["total_hours_spent"],
            "hr.department": ["company_id"],
            "hr.employee": ["company_id", "current_version_id", "parent_id", "user_id"],
            "hr.version": ["department_id"],
        }
    )

    department_id = fields.Many2one(
        comodel_name="hr.department",
        readonly=True,
    )
    manager_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    total_hours_spent = fields.Float(
        string="Hours Spent (Timesheets)",
        readonly=True,
        aggregator="avg",
        groups="hr_timesheet.group_hr_timesheet_user",
    )

    def _select(self):
        return (
            super()._select()
            + """,
            DEP.id as department_id,
            EMP.parent_id as manager_id,
            EMP.id as employee_id,
            NULLIF(T.total_hours_spent, 0) AS total_hours_spent
        """
        )

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
            LEFT JOIN "res_users" U on T.user_id = U.id AND U.company_id = TEAM.company_id
            LEFT JOIN "hr_employee" EMP on EMP.user_id = U.id AND EMP.company_id = TEAM.company_id
            LEFT JOIN hr_version VER ON VER.id = EMP.current_version_id
            LEFT JOIN "hr_department" DEP on VER.department_id = DEP.id AND DEP.company_id = TEAM.company_id
        """
        return from_str
