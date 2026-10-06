from odoo import fields, models


class AutomationRuntime(models.Model):
    _inherit = "automation.runtime"

    marketing_participant_ids = fields.One2many(
        comodel_name="marketing.participant",
        inverse_name="runtime_id",
        string="Marketing Participant",
    )

    def _materialize(self, actions):
        lines = super()._materialize(actions)
        lines._create_missing_marketing_traces()
        return lines
