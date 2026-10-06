from odoo import models


class QualityCheck(models.Model):
    _inherit = "quality.check"

    def action_worksheet_check(self):
        self.check_singleton()
        if not self.env.context.get("quality_wizard_id"):
            wizard = self.env["wizard.quality.check.decide"].create(
                {
                    "check_ids": [self.id],
                    "current_check_id": self.id,
                }
            )
            action = (
                super()
                .with_context(quality_wizard_id=wizard.id)
                .action_worksheet_check()
            )
        else:
            action = super().action_worksheet_check()
        if self.workorder_id and not self.env.context.get("from_worksheet"):
            return self._next()
        return action

    def action_fill_sheet(self):
        self.check_singleton()
        return self.action_quality_worksheet()
