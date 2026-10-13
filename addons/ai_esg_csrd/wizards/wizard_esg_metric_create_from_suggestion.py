from odoo import api, fields, models


class WizardEsgMetricCreateFromSuggestion(models.TransientModel):
    _name = "wizard.esg.metric.create.from.suggestion"
    _description = "AI suggestions of ESG Metrics"

    suggestion_line_ids = fields.One2many(
        comodel_name="wizard.esg.metric.create.from.suggestion.line",
        inverse_name="wizard_id",
    )
    has_one_or_more_selected = fields.Boolean(
        compute="_compute_has_one_or_more_selected"
    )

    @api.depends("suggestion_line_ids.is_selected")
    def _compute_has_one_or_more_selected(self) -> None:
        for wizard in self:
            wizard.has_one_or_more_selected = any(
                wizard.suggestion_line_ids.mapped("is_selected")
            )

    def action_add_suggestions(self) -> dict:
        self.check_singleton()
        metric_vals = [
            {
                "name": line.name,
                "esrs_id": line.esrs_id.id,
                "type": line.type,
                "category": line.category,
                "notes": line.detail,
            }
            for line in self.suggestion_line_ids
            if line.is_selected or self.env.context.get("add_all_suggestions")
        ]
        if metric_vals:
            self.env["esg.metric"].create(metric_vals)
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "success",
                    "message": self.env._("Metrics have been successfully created."),
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }
        return {"type": "ir.actions.act_window_close"}
