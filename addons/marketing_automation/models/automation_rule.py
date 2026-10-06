from odoo import fields, models


class AutomationRule(models.Model):
    _inherit = "automation.rule"

    marketing_campaign_ids = fields.One2many(
        comodel_name="marketing.campaign",
        inverse_name="automation_rule_id",
        string="Marketing Campaign",
    )

    def _workflow_event_labels(self):
        labels = super()._workflow_event_labels()
        if not self.sudo().marketing_campaign_ids:
            return labels
        Activity = self.env["marketing.activity"]
        for code, label in Activity._fields["trigger_type"]._description_selection(
            self.env
        ):
            if code in ("begin", "activity"):
                continue
            if "_not_" in code:
                labels["no_event", code.replace("_not_", "_")] = label
            else:
                labels["event", code] = label
        return labels
