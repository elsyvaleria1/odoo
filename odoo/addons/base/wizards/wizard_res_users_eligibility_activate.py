from odoo import fields, models


class WizardResUsersEligibilityActivate(models.TransientModel):
    _name = "wizard.res.users.eligibility.activate"
    _description = "Activate an Eligibility"

    eligibility_id = fields.Many2one(
        comodel_name="res.users.eligibility",
        required=True,
        ondelete="cascade",
    )
    hours = fields.Float(
        default=1.0,
        required=True,
    )
    justification = fields.Char()

    def action_confirm(self) -> dict[str, str]:
        self.check_singleton()
        self.eligibility_id.action_activate(self.hours, self.justification)
        return {"type": "ir.actions.client", "tag": "reload"}
