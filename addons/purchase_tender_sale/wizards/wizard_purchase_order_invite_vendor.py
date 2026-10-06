from odoo import models


class WizardPurchaseOrderInviteVendor(models.TransientModel):
    _inherit = "wizard.purchase.order.invite.vendor"

    def _prepare_offer_line_values(self, line, partner):
        values = super()._prepare_offer_line_values(line, partner)
        if line.sale_line_id:
            values["sale_line_id"] = line.sale_line_id.id
        return values
