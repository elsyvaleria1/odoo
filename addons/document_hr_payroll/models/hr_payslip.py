import logging
from typing import Self

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class HrPayslip(models.Model):
    _name = "hr.payslip"
    _inherit = ["hr.payslip", "mixin.documents"]

    document_ids = fields.One2many(
        comodel_name="document.document",
        inverse_name="res_id",
        string="Documents",
        domain=[("res_model", "=", "hr.payslip")],
    )
    document_access_url = fields.Char(compute="_compute_document_access_url")

    def _filtered_sendable(self) -> Self:
        return self.filtered(lambda payslip: payslip.state in ("validated", "paid"))

    def _payslip_notification(self, notification_type, message, title=None) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title or self.env._("Send Payslip By Email"),
                "type": notification_type,
                "message": message,
            },
        }

    def action_resend_payslips(self, notify=False):
        if not self.env.user.has_group("hr_payroll.group_hr_payroll_user"):
            _debug.logic("resend_refused", reason="not_payroll_user", payslips=self)
            raise UserError(
                self.env._("You can not send the documents link to the employee.")
            )
        payslips_sudo = self.sudo()
        sendable = payslips_sudo._filtered_sendable()
        wrong_state = payslips_sudo - sendable
        without_email = sendable.filtered(
            lambda payslip: (
                not (
                    payslip.employee_id.private_email or payslip.employee_id.work_email
                )
            )
        )
        sendable -= without_email
        without_document = sendable.filtered(
            lambda payslip: not payslip.document_access_url
        )
        sendable -= without_document
        _debug.pipeline(
            "payslip_resend",
            sendable=sendable,
            wrong_state=len(wrong_state),
            without_email=len(without_email),
            without_document=len(without_document),
        )

        for payslip in sendable:
            template = payslip._get_email_template()
            template.send_mail(
                payslip.id, email_layout_xmlid="mail.mail_notification_light"
            )
            payslip.message_post(
                body=self.env._("The payslip has been re-sent to the employee.")
            )

        skipped = []
        if wrong_state:
            skipped.append(
                self.env._(
                    "A payslip should be validated or paid to be sent to the employee."
                )
            )
        if without_email:
            skipped.append(
                self.env._(
                    'Employee\'s private or work email must be set to use "Send By Email" function:\n%s',
                    "\n".join(without_email.employee_id.mapped("name")),
                )
            )
        if without_document:
            skipped.append(
                self.env._(
                    "Some payslips could not be resend as they do not have related document"
                )
            )

        if not sendable:
            return self._payslip_notification(
                "warning",
                "\n".join(skipped)
                or self.env._("There is no payslip to send to the employee."),
            )
        if not notify and not skipped:
            return None

        sent = self.env._("%s Payslip(s) correctly sent.", len(sendable))
        if skipped:
            return self._payslip_notification("warning", "\n".join([sent, *skipped]))
        return self._payslip_notification("success", sent)

    def _get_document_vals_access_rights(self):
        return {
            "access_via_link": "view",
            "access_internal": "none",
            "is_access_via_link_hidden": True,
        }

    def _get_document_access_ids(self):
        return [(self._get_document_partner(), ("view", False))]

    def _get_document_tags(self):
        return self.company_id.documents_hr_payslips_tags

    def _get_document_partner(self):
        return self.employee_id.user_id.partner_id or self.employee_id.partner_id

    def _get_document_owner(self):
        return self.employee_id.user_id or super()._get_document_owner()

    def _get_document_folder(self):
        _debug.logic(
            "payslip_folder",
            by="employee_user" if self.employee_id.user_id else "worker_pool",
            payslip=self,
        )
        return (
            super()._get_document_folder()
            if self.employee_id.user_id
            else self.company_id._get_or_create_worker_payroll_folder()
        )

    def _check_create_documents(self):
        self.check_singleton()
        return self._get_document_partner().id and (
            bool(self.employee_id.user_id) or self.company_id.documents_hr_settings
        )

    def _get_email_template(self):
        return self.env.ref(
            "document_hr_payroll.mail_template_new_payslip", raise_if_not_found=False
        )

    @api.depends("document_ids.access_url")
    def _compute_document_access_url(self) -> None:
        for payslip in self:
            last_document = payslip.document_ids.sorted("id", reverse=True)[:1]
            payslip.document_access_url = last_document.access_url

    def _check_send_payslip_mail(self):
        self.check_singleton()
        res = super()._check_send_payslip_mail()
        return res and self._check_create_documents()

    @api.model
    def _cron_generate_pdf(self, batch_size=False):
        is_rescheduled = super()._cron_generate_pdf(batch_size=batch_size)
        if is_rescheduled:
            return is_rescheduled

        lines = self.env["hr.payroll.employee.declaration"].search(
            [("pdf_to_post", "=", True)]
        )
        if lines:
            BATCH_SIZE = batch_size or 30
            lines_batch = lines[:BATCH_SIZE]
            _debug.pipeline(
                "declaration_pdf_post", queued=len(lines), batch=len(lines_batch)
            )
            lines_batch._post_pdf()
            lines_batch.write({"pdf_to_post": False})
            undeliverable = lines_batch.filtered(lambda line: not line.document_id)
            if undeliverable:
                _debug.logic(
                    "declaration_dequeued", reason="no_pdf", lines=undeliverable
                )
                _logger.warning(
                    "Dequeued %s employee declaration(s) with no PDF file to post: %s",
                    len(undeliverable),
                    undeliverable.ids,
                )
            if len(lines) > BATCH_SIZE:
                self.env["ir.cron"]._trigger_ref(
                    "hr_payroll.ir_cron_generate_payslip_pdfs"
                )
                return True
        return False
