import logging
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayrollEmployeeDeclaration(models.Model):
    _name = "hr.payroll.employee.declaration"
    _description = "Payroll Employee Declaration"
    _rec_name = "employee_id"

    res_model = fields.Char(
        string="Declaration Model Name",
        index=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Declaration Model Id",
        index=True,
        required=True,
    )
    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        domain="['|', ('active', '=', True), ('active', '=', False)]",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    pdf_file = fields.Binary(
        string="PDF File",
        attachment=False,
        readonly=True,
    )
    pdf_filename = fields.Char()
    pdf_to_generate = fields.Boolean()
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("pdf_to_generate", "Queued PDF generation"),
            ("pdf_generated", "Generated PDF"),
        ],
        compute="_compute_state",
        store=True,
    )

    _unique_employee_sheet = models.Constraint(
        "unique(employee_id, res_model, res_id)",
        "An employee can only have one declaration per sheet.",
    )

    @api.depends("pdf_to_generate", "pdf_file")
    def _compute_state(self):
        for declaration in self:
            if declaration.pdf_to_generate:
                declaration.state = "pdf_to_generate"
            elif declaration.pdf_file:
                declaration.state = "pdf_generated"
            else:
                declaration.state = "draft"

    def _update_pdf(self) -> None:
        report_sudo = self.env["ir.actions.report"].sudo()
        declarations_by_sheet = defaultdict(
            lambda: self.env["hr.payroll.employee.declaration"]
        )
        for declaration in self:
            declarations_by_sheet[(declaration.res_model, declaration.res_id)] += (
                declaration
            )

        for (res_model, res_id), declarations in declarations_by_sheet.items():
            sheet = self.env[res_model].browse(res_id)
            if not sheet.exists():
                _logger.warning("Sheet %s %s does not exist", res_model, res_id)
                continue
            report_id = sheet._get_pdf_report().id
            has_global = any(not d.employee_id for d in declarations)
            if has_global:
                employees = self.env[res_model].browse(res_id).line_ids.employee_id
            else:
                employees = declarations.employee_id
            try:
                rendering_data = sheet._prepare_rendering_data(employees)
            except UserError as e:
                rendering_data = {"error": str(e)}
            if "error" in rendering_data:
                sheet.pdf_error = rendering_data["error"]
                continue
            rendering_data = sheet._prepare_pdf_values_by_employee(rendering_data)

            pdf_files = []
            sheet_count = len(rendering_data)
            counter = 1
            for employee, employee_data in rendering_data.items():
                if (employee and employee not in declarations.employee_id) or (
                    not employee and not has_global
                ):
                    continue
                employee = employee or self.env["hr.employee"]
                _logger.info(
                    "Printing %s (%s/%s)", sheet._description, counter, sheet_count
                )
                counter += 1
                sheet_filename = sheet._get_pdf_filename(employee)
                sheet_file, _dummy = report_sudo.with_context(
                    lang=employee.lang or self.env.lang
                )._render_qweb_pdf(
                    report_id,
                    [employee.id],
                    data={
                        "report_data": employee_data,
                        "employee": employee,
                        "company_id": employee.company_id,
                    },
                )
                pdf_files.append((employee, sheet_filename, sheet_file))
            if pdf_files:
                sheet._process_files(pdf_files)

    @api.model_create_multi
    def create(self, vals_list):
        declarations = super().create(vals_list)
        if any(declaration.pdf_to_generate for declaration in declarations):
            self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")
        return declarations

    def write(self, vals):
        res = super().write(vals)
        if vals.get("pdf_to_generate"):
            self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")
        return res

    def action_generate_pdf(self):
        if self:
            self.write({"pdf_to_generate": True})
            self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")
        else:
            not_generated_declaration_pdfs = self.env[
                "hr.payroll.employee.declaration"
            ].search([("state", "=", "draft")])
            not_generated_declaration_pdfs.write({"pdf_to_generate": True})
            self.env["ir.cron"]._trigger_ref("hr_payroll.ir_cron_generate_payslip_pdfs")
        message = self.env._("PDF generation started. It will be available shortly.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": message,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }

    @api.autovacuum
    def _gc_orphan_declarations(self) -> None:
        orphan_ids = []
        grouped_declarations = self._read_group([], ["res_model"], ["res_id:array_agg"])
        for res_model, res_ids in grouped_declarations:
            existing_ids = set(self.env[res_model].browse(set(res_ids)).exists().ids)
            orphan_ids.extend(
                res_id for res_id in res_ids if res_id not in existing_ids
            )
        if orphan_ids:
            self.browse(orphan_ids).unlink()
