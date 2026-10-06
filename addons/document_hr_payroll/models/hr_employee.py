from odoo import models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def action_resend_payslips(self):
        self.check_singleton()
        if not self.env.user.has_group("hr_payroll.group_hr_payroll_user"):
            _debug.logic("resend_refused", reason="not_payroll_user", employee=self)
            raise UserError(
                self.env._("You can not send the documents link to the employee.")
            )

        title = self.env._("Resend All Employee's Payslips")
        valid_payslips = self.slip_ids._filtered_sendable().filtered(
            "document_access_url"
        )
        if not valid_payslips:
            _debug.logic("resend_refused", reason="no_valid_payslip", employee=self)
            return self.env["hr.payslip"]._payslip_notification(
                "warning",
                self.env._("There is no valid payslip to send to the employee."),
                title=title,
            )
        # Return the payslip-level result: it already reports what was sent
        # and what was skipped (missing email, missing document). Fabricating
        # a success toast here showed "successfully sent" even when every
        # payslip was skipped and no mail was queued.
        return valid_payslips.action_resend_payslips(notify=True)
