from odoo import models
from odoo.exceptions import ValidationError


class WizardMrpProductionUpdateQuantity(models.TransientModel):
    _inherit = "wizard.mrp.production.update.quantity"

    def change_prod_qty(self):
        super().change_prod_qty()
        # if there are quality checks, we should create new checks/update the quantities, etc.
        # if we want to make this feature work, a task should be done to deal with all the possible cases:
        # types of quality check, quantity processed, etc. In the meantime, we block this feature.
        for wizard in self:
            done_checks = self.env["quality.check"].search(
                [
                    "&",
                    ("control_date", "!=", False),
                    "|",
                    ("production_id", "=", wizard.mo_id.id),
                    ("workorder_id", "in", wizard.mo_id.workorder_ids.ids),
                ]
            )
            if done_checks:
                raise ValidationError(
                    self.env._(
                        "You cannot update the quantity to do of an ongoing "
                        "manufacturing order for which quality checks have been performed."
                    )
                )
