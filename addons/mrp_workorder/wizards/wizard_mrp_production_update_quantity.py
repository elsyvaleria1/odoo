from odoo import models
from odoo.exceptions import ValidationError


class WizardMrpProductionUpdateQuantity(models.TransientModel):
    _inherit = "wizard.mrp.production.update.quantity"

    def change_prod_qty(self):
        # if there are quality checks, we should create new checks/update the quantities, etc.
        # if we want to make this feature work, a task should be done to deal with all the possible cases:
        # types of quality check, quantity processed, etc. In the meantime, we block this feature.
        productions = self.mo_id
        if self.env["quality.check"].search_count(
            [
                "&",
                ("control_date", "!=", False),
                "|",
                ("production_id", "in", productions.ids),
                ("workorder_id", "in", productions.workorder_ids.ids),
            ],
            limit=1,
        ):
            raise ValidationError(
                self.env._(
                    "You cannot update the quantity to do of an ongoing "
                    "manufacturing order for which quality checks have been performed."
                )
            )
        return super().change_prod_qty()
