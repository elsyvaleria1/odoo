from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrPayslipUpdateLinePayslipLine(models.TransientModel):
    _name = "wizard.hr.payslip.update.line.payslip.line"
    _description = "Edit payslip lines wizard line"

    name = fields.Char(translate=True)
    sequence = fields.Integer()
    salary_rule_id = fields.Many2one(
        comodel_name="hr.salary.rule",
        string="Rule",
        domain="[('struct_id', '=', struct_id)]",
    )
    code = fields.Char(related="salary_rule_id.code")
    version_id = fields.Many2one(
        related="slip_id.version_id",
        string="Contract",
    )
    employee_id = fields.Many2one(
        related="version_id.employee_id",
        string="Employee",
    )
    rate = fields.Float(
        string="Rate (%)",
        digits="Payroll Rate",
        default=100.0,
    )
    amount = fields.Float(digits="Payroll")
    quantity = fields.Float(
        digits="Payroll",
        default=1.0,
    )
    total = fields.Float(
        digits="Payroll",
        compute="_compute_total",
        store=True,
    )
    slip_id = fields.Many2one(
        related="edit_payslip_lines_wizard_id.payslip_id",
        string="Pay Slip",
    )
    struct_id = fields.Many2one(related="slip_id.struct_id")
    category_id = fields.Many2one(
        related="salary_rule_id.category_id",
        readonly=True,
    )
    ytd = fields.Float(
        string="YTD",
        digits="Payroll",
        readonly=True,
    )

    edit_payslip_lines_wizard_id = fields.Many2one(
        comodel_name="wizard.hr.payslip.update.line",
        required=True,
        ondelete="cascade",
    )

    @api.depends("quantity", "amount", "rate")
    def _compute_total(self) -> None:
        for line in self:
            line.total = float(line.quantity) * line.amount * line.rate / 100

    def _export_to_payslip_line(self) -> list:
        return [
            {
                "sequence": line.sequence,
                "code": line.code,
                "name": line.name,
                "salary_rule_id": line.salary_rule_id.id,
                "version_id": line.version_id.id,
                "employee_id": line.employee_id.id,
                "amount": line.amount,
                "quantity": line.quantity,
                "rate": line.rate,
                "total": line.total,
                "ytd": line.ytd,
                "slip_id": line.slip_id.id,
            }
            for line in self
        ]
