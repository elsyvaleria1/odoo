from odoo import fields, models


class HrContractSalaryResume(models.Model):
    _inherit = "hr.contract.salary.resume"

    def _get_fields_available(self):
        result = super()._get_fields_available()
        return result + [
            ("BASIC", "Basic"),
            ("SALARY", "Salary"),
            ("GROSS", "Taxable Salary"),
            ("NET", "Net"),
        ]

    code = fields.Selection(selection=_get_fields_available)
    value_type = fields.Selection(
        selection_add=[("payslip", "Payslip Value"), ("sum",)],
        ondelete={"payslip": "set default"},
        help="Pick how the value of the information is computed:\n"
        "Fixed value: Set a determined value static for all links\n"
        "Employee Record value: Get the value from a field on the Employee Record\n"
        "Payslip value: Get the value from a field on the payslip record\n"
        "Sum of Benefits value: You can pick in all benefits and compute a sum of them\n"
        "Monthly Total: The information will be a total of all the information in the category Monthly Benefits",
    )
