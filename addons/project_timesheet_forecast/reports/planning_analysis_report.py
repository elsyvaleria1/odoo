from odoo import api, fields, models
from odoo.tools import frozendict


class PlanningAnalysisReport(models.Model):
    _inherit = "planning.analysis.report"
    _depends = frozendict(
        {
            "planning.slot": [
                "effective_hours",
                "effective_hours_cost",
                "percentage_hours",
            ],
        }
    )

    percentage_hours = fields.Float(
        string="Progress (%)",
        readonly=True,
        aggregator="avg",
        groups="hr_timesheet.group_hr_timesheet_approver",
    )
    effective_hours = fields.Float(
        string="Effective Time",
        readonly=True,
        groups="hr_timesheet.group_hr_timesheet_approver",
        help="Number of time recorded on the employee's Timesheets for this task (and its sub-tasks) during the timeframe of the shift.",
    )
    remaining_hours = fields.Float(
        string="Time Remaining",
        readonly=True,
        groups="hr_timesheet.group_hr_timesheet_approver",
        help="Allocated time minus the effective time.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
    )
    allocated_hours_cost = fields.Monetary(
        string="Allocated Time Cost",
        readonly=True,
        groups="hr.group_hr_user",
    )
    effective_hours_cost = fields.Monetary(
        string="Effective Time Cost",
        readonly=True,
        groups="hr.group_hr_user",
    )

    @api.model
    def _select(self):
        return (
            super()._select()
            + """,
            S.effective_hours AS effective_hours,
            S.percentage_hours AS percentage_hours,
            (S.allocated_hours - S.effective_hours) AS remaining_hours,
            S.allocated_hours * E.hourly_cost AS allocated_hours_cost,
            S.effective_hours_cost AS effective_hours_cost,
            CO.currency_id AS currency_id
        """
        )

    @api.model
    def _join(self):
        return (
            super()._join()
            + """
            LEFT JOIN res_company CO ON CO.id = S.company_id
        """
        )

    @api.model
    def _group_by(self):
        return (
            super()._group_by()
            + """,
            S.effective_hours, S.effective_hours_cost, S.allocated_hours,
            E.hourly_cost, CO.currency_id
        """
        )
