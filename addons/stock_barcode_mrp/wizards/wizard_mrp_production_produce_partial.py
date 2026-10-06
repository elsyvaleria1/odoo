from odoo import models


class WizardMrpProductionProducePartial(models.TransientModel):
    _inherit = "wizard.mrp.production.produce.partial"

    def action_backorder(self):
        res = super().action_backorder()
        if self.env.context.get("barcode_trigger", False):
            return True
        return res
