from odoo import fields, models


class HrContractSalaryResumeCategory(models.Model):
    _name = "hr.contract.salary.resume.category"
    _description = "Salary Package Resume Category"
    _order = "sequence"

    name = fields.Char(translate=True)
    sequence = fields.Integer(default=100)
    periodicity = fields.Selection(
        selection=[("monthly", "Monthly"), ("yearly", "Yearly")]
    )


class HrContractSalaryResume(models.Model):
    _name = "hr.contract.salary.resume"
    _description = "Salary Package Resume"
    _order = "sequence"

    def _get_fields_available(self):
        return [
            (field, description["string"])
            for field, description in self.env["hr.version"].fields_get().items()
            if description["type"] not in ("one2many", "many2one", "many2many")
        ]

    name = fields.Char(translate=True)
    sequence = fields.Integer(default=100)
    value_type = fields.Selection(
        selection=[
            ("fixed", "Fixed Value"),
            ("version", "Employee Record Value"),
            ("sum", "Sum of Benefits Values"),
            ("monthly_total", "Monthly Total"),
        ],
        default="fixed",
        required=True,
        help="Pick how the value of the information is computed:\n"
        "Fixed value: Set a determined value static for all links\n"
        "Employee Record value: Get the value from a field on the Employee Record\n"
        "Sum of Benefits value: You can pick in all benefits and compute a sum of them\n"
        "Monthly Total: The information will be a total of all the information in the category Monthly Benefits",
    )
    benefit_ids = fields.Many2many(comodel_name="hr.contract.salary.benefit")
    code = fields.Selection(selection=_get_fields_available)
    fixed_value = fields.Float()
    category_id = fields.Many2one(
        comodel_name="hr.contract.salary.resume.category",
        required=True,
        help="Pick a category to display this information",
    )
    structure_type_id = fields.Many2one(
        comodel_name="hr.payroll.structure.type",
        string="Salary Structure Type",
    )
    impacts_monthly_total = fields.Boolean(
        help="If checked, the value of this information will be computed in all information set as Monthly Total"
    )
    uom = fields.Selection(
        selection=[("days", "Days"), ("percent", "Percent"), ("currency", "Currency")],
        string="Unit of Measure",
        default="currency",
    )
    active = fields.Boolean(default=True)
