from odoo import fields, models


class MailActivity(models.Model):
    _inherit = "mail.activity"

    automation_runtime_line_id = fields.Many2one(
        comodel_name="automation.runtime.line",
        string="Workflow Step",
        index="btree_not_null",
        ondelete="cascade",
        help="The Approval step waiting on this activity",
    )

    def _action_done(self, feedback=False, attachment_ids=None):
        # an approver answers as themself and moves no run: the dispatcher
        # settles the step their activity holds, running the workflow as its
        # rule does
        approvals = self.filtered("automation_runtime_line_id")
        result = super()._action_done(feedback=feedback, attachment_ids=attachment_ids)
        if approvals:
            self.env["automation.runtime"]._request_dispatch()
        return result

    def unlink(self):
        # whoever may unlink an activity need not read it; an approval's
        # activity is its approver's, who reads it
        approvals = self._filtered_access("read").filtered("automation_runtime_line_id")
        result = super().unlink()
        if approvals:
            self.env["automation.runtime"]._request_dispatch()
        return result
