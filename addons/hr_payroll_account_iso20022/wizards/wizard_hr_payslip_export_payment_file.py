import base64

from odoo import fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrPayslipExportPaymentFile(models.TransientModel):
    _inherit = "wizard.hr.payslip.export.payment.file"

    export_format = fields.Selection(
        selection_add=[("sepa", "SEPA"), ("iso20022_ch", "Swiss ISO20022")],
        default="sepa",
        ondelete={"sepa": "set csv", "iso20022_ch": "set csv"},
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Bank Journal",
        default=lambda self: self.env["account.journal"].search(
            [("type", "=", "bank")], limit=1
        ),
        required=True,
    )

    def _create_sepa_binary(self):
        payments_data = []
        for slip in self.payslip_ids.filtered(
            lambda p: p.state == "validated" and p.net_wage > 0
        ):
            payments_data.extend(
                slip._acquire_iso20022_payments_data(
                    self.journal_id, self.date_effective
                )
            )
        payment_method_code = self.env.context.get("payment_method") or "sepa_ct"
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "sepa_payments_collected",
                wizard=self,
                payslips=self.payslip_ids,
                eligible=len(
                    self.payslip_ids.filtered(
                        lambda p: p.state == "validated" and p.net_wage > 0
                    )
                ),
                payments=len(payments_data),
                payment_method=payment_method_code,
                journal=self.journal_id,
            )

        xml_doc = (
            self.journal_id.sudo()
            .with_context(
                sepa_payroll_sala=True,
                l10n_be_hr_payroll_sepa_salary_payment=self.journal_id.company_id.tax_config_id.account_fiscal_country_id.code
                == "BE",
            )
            .create_iso20022_credit_transfer(
                payments=payments_data,
                payment_method_code=payment_method_code,
                batch_booking=True,
            )
        )
        return base64.encodebytes(xml_doc)

    def _perform_checks(self) -> None:
        super()._perform_checks()
        if self.export_format in ["sepa", "iso20022_ch"]:
            if self.date_effective < fields.Date.today():
                _debug.logic(
                    "sepa_refused",
                    reason="payment_date_in_the_past",
                    wizard=self,
                    date_effective=self.date_effective,
                )
                raise ValidationError(
                    self.env._("The payment date cannot be in the past.")
                )
            employees = self.payslip_ids.employee_id.filtered(
                lambda e: not e.partner_id
            )
            if employees:
                raise UserError(
                    self.env._(
                        "Some employees (%s) don't have a work contact.",
                        employees.mapped("name"),
                    )
                )
            employees = self.payslip_ids.employee_id.filtered(
                lambda e: e.partner_id and not e.partner_id.name
            )
            if employees:
                raise UserError(
                    self.env._(
                        "Some employees (%s) don't have a valid name on the work contact.",
                        employees.mapped("name"),
                    )
                )
            if self.journal_id.bank_account_id.acc_type != "iban":
                _debug.logic(
                    "sepa_refused",
                    reason="journal_account_is_not_an_iban",
                    wizard=self,
                    journal=self.journal_id,
                    bank_account=self.journal_id.bank_account_id,
                    acc_type=self.journal_id.bank_account_id.acc_type,
                )
                raise UserError(
                    self.env._(
                        "The journal '%s' requires a proper IBAN account to pay via SEPA. "
                        "Please configure it first.",
                        self.journal_id.name,
                    )
                )

    def generate_payment_report(self) -> None:
        super().generate_payment_report()
        if self.export_format in ["sepa", "iso20022_ch"]:
            if self.export_format == "sepa":
                payment_report = self.with_context(
                    payment_method="sepa_ct"
                )._create_sepa_binary()
            elif self.export_format == "iso20022_ch":
                payment_report = self.with_context(
                    payment_method="iso20022_ch"
                )._create_sepa_binary()
            _debug.lifecycle(
                "sepa_report_generated",
                wizard=self,
                export_format=self.export_format,
                run=self.payslip_run_id,
                payslips=self.payslip_ids,
                bytes=len(payment_report),
            )
            self._write_file(payment_report, ".xml")
