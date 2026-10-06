from odoo import api, models


class WizardSaleOrderAddShipping(models.TransientModel):
    _inherit = "wizard.sale.order.add.shipping"

    @api.depends("carrier_id")
    def _compute_invoicing_message(self) -> None:
        super()._compute_invoicing_message()
        if self.carrier_id.invoice_policy == "real":
            self.invoicing_message = self.env._(
                "The shipping price will be set once the delivery is done."
            )
