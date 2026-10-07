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
        # an approver answers as themself; releasing the step writes the run,
        # which is the system's to write (automation.runtime is cud for
        # base.group_system only), as starting the run was the rule's
        lines = self.automation_runtime_line_id
        result = super()._action_done(feedback=feedback, attachment_ids=attachment_ids)
        lines.sudo()._check_approval_complete()
        return result

    def unlink(self):
        # whoever may unlink an activity need not read it; an approval's
        # activity is its approver's, who reads it
        lines = self._filtered_access("read").automation_runtime_line_id
        result = super().unlink()
        lines.exists().sudo()._fail_missing_approval()
        return result
