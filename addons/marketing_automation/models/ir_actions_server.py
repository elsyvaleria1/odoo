from odoo import fields, models


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    marketing_activity_ids = fields.One2many(
        comodel_name="marketing.activity",
        inverse_name="node_id",
        string="Marketing Activity",
    )

    def _workflow_step_detail(self):
        activity = self.sudo().marketing_activity_ids[:1]
        if not activity:
            return super()._workflow_step_detail()
        kind = dict(activity._fields["activity_type"]._description_selection(self.env))[
            activity.activity_type
        ]
        subject = activity._get_workflow_subject()
        return f"{kind}: {subject}" if subject else kind

    def _execute_runtime_lines(self, lines):
        activity = self.sudo().marketing_activity_ids[:1]
        if not activity:
            return super()._execute_runtime_lines(lines)
        return activity._execute_lines(lines)
