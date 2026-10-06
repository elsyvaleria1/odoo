from odoo import fields, models


class HrPayrollStructureType(models.Model):
    _inherit = "hr.payroll.structure.type"
    _description = "Salary Structure Type"

    salary_benefits_ids = fields.One2many(
        comodel_name="hr.contract.salary.benefit",
        inverse_name="structure_type_id",
    )
