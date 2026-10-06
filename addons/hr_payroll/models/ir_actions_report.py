from itertools import groupby

from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_qweb_pdf_documents(self, report_ref, res_ids=None, data=None):
        payslip_ids, _data = self._normalize_render_args(res_ids, data, "pdf")
        report = self._get_report(report_ref)
        if payslip_ids and report.model == "hr.payslip":
            # Every payslip report honours the error gate, not only the
            # default one: a payslip with errors must not print at all.
            self.env["hr.payslip"].browse(payslip_ids)._check_printable()
        payslip_report = self.env.ref("hr_payroll.action_report_payslip", False)
        if not payslip_ids or report != payslip_report:
            return super()._render_qweb_pdf_documents(
                report_ref, res_ids=res_ids, data=data
            )

        payslips = self.env["hr.payslip"].browse(payslip_ids)
        if not self._is_pdf_rendering_enabled():
            return super()._render_qweb_pdf_documents(
                report_ref, res_ids=res_ids, data=data
            )

        report_by_payslip = {
            payslip: slip_report
            for slip_report, slips in payslips._get_pdf_reports().items()
            for payslip in slips
        }
        documents = []
        for (slip_report, lang), slips in groupby(
            payslips,
            key=lambda slip: (
                report_by_payslip[slip],
                slip.employee_id.lang or slip.env.lang,
            ),
        ):
            renderer = super(IrActionsReport, self.with_context(lang=lang))
            documents.extend(
                renderer._render_qweb_pdf_documents(
                    slip_report, [slip.id for slip in slips], data=data
                )[0]
            )
        return documents, "pdf"
