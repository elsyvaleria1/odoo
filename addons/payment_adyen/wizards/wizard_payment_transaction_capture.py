from odoo import api, fields, models


class WizardPaymentTransactionCapture(models.TransientModel):
    _inherit = "wizard.payment.transaction.capture"

    has_adyen_tx = fields.Boolean(compute="_compute_has_adyen_tx")

    @api.depends("transaction_ids")
    def _compute_has_adyen_tx(self) -> None:
        for wizard in self:
            wizard.has_adyen_tx = any(
                tx.provider_code == "adyen" for tx in wizard.transaction_ids
            )
