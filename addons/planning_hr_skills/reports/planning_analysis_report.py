from odoo import api, fields, models


class PlanningAnalysisReport(models.Model):
    _inherit = "planning.analysis.report"

    employee_skill_ids = fields.One2many(
        comodel_name="hr.employee.skill",
        string="Skills",
        compute="_compute_employee_skill_ids",
        search="_search_employee_skill_ids",
    )

    def _compute_employee_skill_ids(self) -> None:
        for slot in self:
            slot.employee_skill_ids = slot.employee_id.current_employee_skill_ids

    @api.model
    def _search_employee_skill_ids(self, operator, value) -> list:
        return [("employee_id.current_employee_skill_ids", operator, value)]
