from odoo import fields, models


class WizardGamificationGoalUpdateCurrent(models.TransientModel):
    """Wizard to update a manual goal"""

    _name = "wizard.gamification.goal.update.current"
    _description = "Gamification Goal Wizard"

    goal_id = fields.Many2one(
        comodel_name="gamification.goal",
        required=True,
    )
    current = fields.Float()

    def action_update_current(self) -> None:
        for wiz in self:
            wiz.goal_id.write(
                {
                    "current": wiz.current,
                    "to_update": False,
                }
            )
            wiz.goal_id.update_goal()
