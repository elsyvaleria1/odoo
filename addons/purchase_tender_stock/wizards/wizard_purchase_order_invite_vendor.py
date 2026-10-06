from odoo import Command, models


class WizardPurchaseOrderInviteVendor(models.TransientModel):
    _inherit = "wizard.purchase.order.invite.vendor"

    def _prepare_offer_values(self):
        values = super()._prepare_offer_values()
        origin = self.origin_order_id
        if not origin:
            return values
        for vals in values:
            vals.update(
                {
                    "picking_type_id": origin.picking_type_id.id,
                    "reference_ids": [Command.set(origin.reference_ids.ids)],
                }
            )
        return values

    def _prepare_offer_line_values(self, line, partner):
        values = super()._prepare_offer_line_values(line, partner)
        if line.move_dest_ids:
            values["move_dest_ids"] = [Command.set(line.move_dest_ids.ids)]
        return values
