import base64
import logging
from datetime import datetime

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MixinHrPayrollDeclaration(models.AbstractModel):
    _name = "mixin.hr.payroll.declaration"
    _inherit = ["mixin.hr.payroll.country.restricted"]
    _description = "Payroll Declaration Mixin"

    def _selection_years(self) -> list:
        current_year = datetime.now().year
        return [(str(i), i) for i in range(1990, current_year + 1)]

    create_date = fields.Datetime(
        string="Created on",
        readonly=True,
    )
    year = fields.Selection(
        selection="_selection_years",
        default=lambda x: str(datetime.now().year - 1),
        required=True,
    )
    line_ids = fields.One2many(
        comodel_name="hr.payroll.employee.declaration",
        inverse_name="res_id",
        string="Declarations",
    )
    lines_count = fields.Count(
        count_of="line_ids",
        string="Eligible Employees",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    pdf_error = fields.Text(string="PDF Error Message")

    def unlink(self):
        self.line_ids.unlink()  # We need to unlink the child line_ids as well to prevent orphan records
        return super().unlink()

    def action_generate_declarations(self):
        for sheet in self:
            if not sheet.line_ids:
                raise UserError(
                    self.env._(
                        "There is no declaration to generate for the given period"
                    )
                )

    def action_view_declarations(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Employee Declarations"),
            "res_model": "hr.payroll.employee.declaration",
            "type": "ir.actions.act_window",
            "views": [(False, "list"), (False, "form")],
            "view_mode": "list,form",
            "domain": [("res_id", "=", self.id), ("res_model", "=", self._name)],
            "context": {"default_res_model": self._name, "default_res_id": self.id},
        }

    def action_generate_pdf(self):
        return self.line_ids.action_generate_pdf()

    def _prepare_pdf_values_by_employee(self, rendering_data):
        return rendering_data

    def _prepare_rendering_data(self, employees):
        return {}

    def _process_files(self, files) -> None:
        self.check_singleton()
        self.pdf_error = False
        lines_by_employee = self.line_ids.grouped("employee_id")
        for employee, filename, data in files:
            line = lines_by_employee.get(employee, self.line_ids.browse())
            line.write(
                {
                    "pdf_file": base64.encodebytes(data),
                    "pdf_filename": filename,
                }
            )

    def _get_pdf_report(self):
        return False

    def _get_pdf_filename(self, employee) -> str:
        self.check_singleton()
        return self.env._(
            "%(employee_name)s-declaration-%(year)s",
            employee_name=employee.legal_name,
            year=self.year,
        )
