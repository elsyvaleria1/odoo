from odoo import fields, models


class AutomationRuntimeLine(models.Model):
    _inherit = "automation.runtime.line"

    marketing_trace_ids = fields.One2many(
        comodel_name="marketing.trace",
        inverse_name="line_id",
        string="Marketing Traces",
    )

    def action_mark_done(self):
        res = super().action_mark_done()
        self.edge_out_ids.target_line_id._create_missing_marketing_traces()
        return res

    def action_mark_error(self, error_msg):
        res = super().action_mark_error(error_msg)
        self.edge_out_ids.target_line_id._create_missing_marketing_traces()
        return res

    def _create_missing_marketing_traces(self) -> None:
        """Create absent traces for reached lines with participants and activities.

        A line is reached if it has no incoming edge or at least one predecessor
        is done, errored or canceled. Existing traces are left unchanged.

        :rtype: None
        """
        reached = self.filtered(
            lambda line: (
                not line.marketing_trace_ids
                and (
                    not line.edge_in_ids
                    or {"done", "error", "cancel"}
                    & set(line.edge_in_ids.source_line_id.mapped("state"))
                )
            ),
        )
        participants = reached.runtime_id.marketing_participant_ids
        if not participants:
            return
        participant_by_runtime = {
            participant.runtime_id.id: participant for participant in participants
        }
        activities = (
            self.env["marketing.activity"]
            .sudo()
            .search([("node_id", "in", reached.action_id.ids)])
        )
        activity_by_node = {activity.node_id.id: activity for activity in activities}
        self.env["marketing.trace"].sudo().create(
            [
                {
                    "line_id": line.id,
                    "participant_id": participant_by_runtime[line.runtime_id.id].id,
                    "activity_id": activity_by_node[line.action_id.id].id,
                }
                for line in reached
                if line.runtime_id.id in participant_by_runtime
                and line.action_id.id in activity_by_node
            ]
        )
