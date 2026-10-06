from odoo import fields, models


class HrPayrollNote(models.Model):
    _name = "hr.payroll.note"
    _description = "Payroll Note"

    name = fields.Char(required=True)
    note = fields.Html(required=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
