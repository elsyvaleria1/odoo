from odoo import models

from .hr_leave import LEAVE_TO_DEFER_ACTIVITY_XMLID


class MailActivity(models.Model):
    _inherit = "mail.activity"

    def _action_done(self, feedback=False, attachment_ids=None):
        leave_activities = self.filtered(
            lambda act: act.res_model == "hr.leave" and act.res_id
        )
        if leave_activities:
            type_to_defer_id = self.env["ir.model.data"]._xmlid_to_res_id(
                LEAVE_TO_DEFER_ACTIVITY_XMLID,
                raise_if_not_found=False,
            )
            if type_to_defer_id:
                leave_activities = leave_activities.filtered(
                    lambda act: act.activity_type_id.id == type_to_defer_id
                )
        if leave_activities:
            # The activity being completed IS the "defer to next payslip"
            # activity, so the leave it points to has just been reported —
            # matching hr.leave.activity_feedback()'s equivalent write for
            # the same activity type.
            self.env["hr.leave"].browse(leave_activities.mapped("res_id")).write(
                {"payslip_state": "done"}
            )
        return super()._action_done(feedback=feedback, attachment_ids=attachment_ids)
