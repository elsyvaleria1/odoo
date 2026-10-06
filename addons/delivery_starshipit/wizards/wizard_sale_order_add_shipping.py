from odoo import models


class WizardSaleOrderAddShipping(models.TransientModel):
    _inherit = "wizard.sale.order.add.shipping"

    def create_new_starshipit_delivery_method(self):
        if self.delivery_type != "starshipit":
            return None

        order_vals = {
            "order_id": self.order_id.id,
            "carrier_id": self.carrier_id.id,
            "total_weight": self.total_weight,
            "destination_partner_id": self.order_id.partner_id.id,
        }
        return self.carrier_id.with_context(
            create_new_carrier=True, order_vals=order_vals
        ).starshipit_action_load_shipping_carriers()
