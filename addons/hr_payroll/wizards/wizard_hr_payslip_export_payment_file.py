import base64
import csv
from collections import defaultdict
from io import StringIO

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_amount, format_date


class WizardHrPayslipExportPaymentFile(models.TransientModel):
    _name = "wizard.hr.payslip.export.payment.file"

    _description = "HR Payroll Payment Report Wizard"

    payslip_run_id = fields.Many2one(
        comodel_name="hr.payslip.run",
        check_company=True,
    )
    payslip_ids = fields.Many2many(
        comodel_name="hr.payslip",
        required=True,
        check_company=True,
    )
    export_format = fields.Selection(
        selection=[
            ("csv", "CSV"),
        ],
        default="csv",
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
    )
    date_effective = fields.Date(
        string="Payment Date",
        default=fields.Date.context_today,
        required=True,
        help="Payment Entry Date: the banking day on which you intend the payslip batch to be settled.",
    )
    include_partners = fields.Boolean(
        string="Include Partner Payments",
        help="Add one line per third party owed a company contribution by the "
        "salary rules of the selected payslips.",
    )

    @api.depends("payslip_ids")
    def _compute_company_id(self):
        for wizard in self:
            wizard.company_id = wizard.payslip_ids[:1].company_id

    def _get_company_for_payment_file(
        self, *, require_single: bool = False
    ) -> models.BaseModel:
        self.check_singleton()
        if self.payslip_run_id:
            return self.payslip_run_id["company_id"]
        companies = self.payslip_ids["company_id"]
        if require_single and len(companies) > 1:
            raise UserError(
                self.env._(
                    "Payment reports can only be generated for one company at a time"
                )
            )
        return companies[:1]

    def _get_payslips_to_process(self):
        return self.payslip_ids.filtered(
            lambda p: p.state == "validated" and p.net_wage > 0
        )

    def _create_csv_binary(self):
        output = StringIO()
        report_data = csv.writer(output)
        report_data.writerow(
            [
                self.env._("Sequence"),
                self.env._("Payment Date"),
                self.env._("Report Date"),
                self.env._("Payslip Period"),
                self.env._("Employee name"),
                self.env._("Bank account"),
                self.env._("BIC"),
                self.env._("Amount to pay"),
            ]
        )
        rows = []
        index = 1
        for slip in self._get_payslips_to_process():
            legal_name = slip.employee_id.legal_name
            allocations = slip.compute_salary_allocations()
            if not allocations:
                continue
            for ba in slip.employee_id.salary_bank_account_ids:
                amount = allocations[str(ba.id)]
                if amount == 0:
                    continue
                rows.append(
                    (
                        str(index),
                        format_date(self.env, self.date_effective),
                        format_date(self.env, fields.Date.today()),
                        format_date(self.env, slip.date_from)
                        + " - "
                        + format_date(self.env, slip.date_to),
                        legal_name,
                        ba.acc_number,
                        ba.bank_bic or "",
                        format_amount(self.env, amount, slip.currency_id),
                    )
                )
                index += 1
        if self.include_partners:
            period = (
                format_date(self.env, min(self.payslip_ids.mapped("date_from")))
                + " - "
                + format_date(self.env, max(self.payslip_ids.mapped("date_to")))
            )
            for partner, amount in self._get_partner_contributions().items():
                bank_account = partner.bank_account_ids[:1]
                rows.append(
                    (
                        str(index),
                        format_date(self.env, self.date_effective),
                        format_date(self.env, fields.Date.today()),
                        period,
                        partner.name,
                        bank_account.acc_number or "",
                        bank_account.bank_bic or "",
                        format_amount(self.env, amount, self.company_id.currency_id),
                    )
                )
                index += 1
        report_data.writerows(rows)
        return base64.encodebytes(output.getvalue().encode())

    def _get_partner_contributions(self):
        contributions = defaultdict(float)
        for line in self.payslip_ids.line_ids.filtered("salary_rule_id.partner_id"):
            contributions[line.salary_rule_id.partner_id] += line.total
        return contributions

    def _write_file(self, payment_report, extension, filename=""):
        if self.payslip_run_id:
            batch_filename = filename or self.env._(
                "Payment Report - %(batch_name)s", batch_name=self.payslip_run_id.name
            )
            self.payslip_run_id.write(
                {
                    "payment_report": payment_report,
                    "payment_report_filename": batch_filename + extension,
                    "payment_report_format": dict(
                        self._fields["export_format"]._description_selection(self.env)
                    )[self.export_format],
                    "payment_report_date": fields.Date.today(),
                }
            )

        for payslip in self.payslip_ids:
            payslip_filename = filename or self.env._(
                "Payment Report - %(dates)s - %(employee_name)s",
                dates=payslip._get_period_name({}),
                employee_name=payslip.employee_id.legal_name,
            )
            payslip.write(
                {
                    "payment_report": payment_report,
                    "payment_report_filename": payslip_filename + extension,
                    "payment_report_date": fields.Date.today(),
                }
            )

    def _perform_checks(self) -> None:
        if not self.payslip_ids:
            raise ValidationError(
                self.env._("There should be at least one payslip to generate the file.")
            )
        if not self._get_payslips_to_process():
            raise ValidationError(
                self.env._(
                    "There is no valid payslip (validated and net wage > 0) to generate the file."
                )
            )

    def _write_payment_date(self) -> None:
        self._get_payslips_to_process().write({"paid_date": self.date_effective})

    def generate_payment_report(self) -> None:
        self.check_singleton()
        if self.payslip_ids.filtered("error_count"):
            raise ValidationError(self._get_error_message())
        self._perform_checks()
        self._write_payment_date()
        if self.export_format == "csv":
            payment_report = self._create_csv_binary()
            self._write_file(payment_report, ".csv")
