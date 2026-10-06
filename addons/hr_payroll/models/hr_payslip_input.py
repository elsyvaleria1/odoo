from odoo import fields, models


class HrPayslipInput(models.Model):
    _name = "hr.payslip.input"
    _description = "Payslip Input"
    _order = "payslip_id, sequence"

    name = fields.Char(string="Description")
    payslip_id = fields.Many2one(
        comodel_name="hr.payslip",
        string="Pay Slip",
        index=True,
        required=True,
        ondelete="cascade",
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        related="payslip_id.employee_id",
        readonly=True,
    )
    date_from = fields.Date(
        related="payslip_id.date_from",
        readonly=True,
    )
    sequence = fields.Integer(
        default=10,
        index=True,
        required=True,
    )
    input_type_id = fields.Many2one(
        comodel_name="hr.payslip.input.type",
        string="Type",
        required=True,
        domain="[('id', 'in', _allowed_input_type_ids)]",
    )
    _allowed_input_type_ids = fields.Many2many(
        comodel_name="hr.payslip.input.type",
        related="payslip_id.struct_id.input_line_type_ids",
    )
    code = fields.Char(
        related="input_type_id.code",
        readonly=True,
        help="The code that can be used in the salary rules",
    )
    amount = fields.Float(
        digits="Payroll Rate",
        help="It is used in computation. E.g. a rule for salesmen having 1%% commission of basic salary per product can defined in expression like: result = inputs['SALEURO'].amount * version.wage * 0.01.",
    )
    version_id = fields.Many2one(
        related="payslip_id.version_id",
        string="Employee Record",
        readonly=True,
        required=True,
        help="The version this input should be applied to",
    )
