from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrPayslipUpdateLineWorkedDays(models.TransientModel):
    _name = "wizard.hr.payslip.update.line.worked_days"
    _description = "Edit payslip line wizard worked days"

    name = fields.Char(related="work_entry_type_id.name")
    slip_id = fields.Many2one(
        related="edit_payslip_lines_wizard_id.payslip_id",
        string="PaySlip",
    )
    sequence = fields.Integer()
    code = fields.Char(related="work_entry_type_id.code")
    work_entry_type_id = fields.Many2one(comodel_name="hr.work.entry.type")
    number_of_days = fields.Float(string="Number of Days")
    number_of_hours = fields.Float(string="Number of Hours")
    amount = fields.Float()
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

    def _export_to_worked_days_line(self) -> list:
        return [
            {
                "name": line.name,
                "sequence": line.sequence,
                "code": line.code,
                "work_entry_type_id": line.work_entry_type_id.id,
                "number_of_days": line.number_of_days,
                "number_of_hours": line.number_of_hours,
                "amount": line.amount,
                "ytd": line.ytd,
                "payslip_id": line.slip_id.id,
            }
            for line in self
        ]
