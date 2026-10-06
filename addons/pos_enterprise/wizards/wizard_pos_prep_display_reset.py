from odoo import models


class WizardPosPrepDisplayReset(models.TransientModel):
    _name = "wizard.pos.prep.display.reset"
    _description = "Reset all current order in a preparation display"

    def reset_all_orders(self) -> None:
        preparation_display = self.env["pos.prep.display"].search(
            [("id", "=", self.env.context["prep_display_id"])]
        )
        preparation_display.reset()
