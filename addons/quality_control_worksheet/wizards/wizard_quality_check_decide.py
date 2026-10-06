from odoo import fields, models


class WizardQualityCheckDecide(models.TransientModel):
    _inherit = "wizard.quality.check.decide"

    worksheet_template_id = fields.Many2one(
        related="current_check_id.worksheet_template_id"
    )

    def action_generate_next_window(self):
        if self.is_last_check:
            return super().action_generate_next_window()
        next_check_id = self.check_ids[self.position_current_check]
        if next_check_id.test_type == "worksheet":
            return self.check_ids.action_view_quality_check_wizard(next_check_id.id)
        return super().action_generate_next_window()

    def action_generate_previous_window(self):
        if self.env.context.get("from_failure_form"):
            check_id = self.current_check_id
        else:
            check_id = self.check_ids[self.position_current_check - 2]
        if check_id.test_type == "worksheet":
            return self.check_ids.action_view_quality_check_wizard(check_id.id)
        return super().action_generate_previous_window()
