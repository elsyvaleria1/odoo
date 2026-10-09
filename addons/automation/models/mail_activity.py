from odoo import fields, models
from odoo.exceptions import AccessError


class MailActivity(models.Model):
    _inherit = "mail.activity"

    automation_runtime_line_id = fields.Many2one(
        comodel_name="automation.runtime.line",
        string="Workflow Step",
        index="btree_not_null",
        ondelete="cascade",
        write_groups="base.group_system",
        help="The Approval step waiting on this activity",
    )

    def write(self, vals):
        identity_fields = {"user_id", "res_id", "res_model_id"} & vals.keys()
        changed = self.browse()
        if identity_fields:
            changed = self.filtered(
                lambda activity: (
                    activity.automation_runtime_line_id
                    and any(
                        (activity[name] if name == "res_id" else activity[name].id)
                        != vals[name]
                        for name in identity_fields
                    )
                )
            )
        if not changed:
            return super().write(vals)
        with self.env.cr.savepoint():
            changed._record_approval_decision("withdrawn")
            result = super().write(vals)
            self.env["automation.runtime"]._request_dispatch()
        return result

    def _action_done(self, feedback=False, attachment_ids=None):
        approvals = self.filtered(
            lambda activity: activity.active and activity.automation_runtime_line_id
        )
        if not approvals:
            return super()._action_done(
                feedback=feedback, attachment_ids=attachment_ids
            )
        if not self.env.su and any(
            activity.user_id != self.env.user for activity in approvals
        ):
            raise AccessError(
                self.env._(
                    "Only the assigned approver may complete a workflow approval."
                )
            )
        with self.env.cr.savepoint():
            result = super()._action_done(
                feedback=feedback, attachment_ids=attachment_ids
            )
            approvals.exists()._record_approval_decision("approved")
            self.env["automation.runtime"]._request_dispatch()
        return result

    def unlink(self):
        approvals = self._filtered_access("read").filtered("automation_runtime_line_id")
        if not approvals:
            return super().unlink()
        with self.env.cr.savepoint():
            approvals._record_approval_decision("withdrawn")
            result = super().unlink()
            self.env["automation.runtime"]._request_dispatch()
        return result

    def _record_approval_decision(self, state):
        decisions = (
            self.env["automation.approval"]
            .with_privilege(
                "automation.privilege_record_approval",
                reason="record the decision of an activity its actor may change",
            )
            .search([("activity_id", "in", self.ids), ("state", "=", "pending")])
        )
        decisions.write(
            {
                "state": state,
                "needs_settlement": True,
                "decided_at": self.env.cr.now(),
                "decided_by_id": self.env.uid,
            }
        )
