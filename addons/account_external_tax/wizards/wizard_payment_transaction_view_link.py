from odoo import api, models


class WizardPaymentTransactionViewLink(models.TransientModel):
    _inherit = "wizard.payment.transaction.view.link"

    @api.model
    def default_get(self, fields):
        res_id = self.env.context.get("active_id")
        res_model = self.env.context.get("active_model")

        if res_id and res_model:
            self.env[res_model].browse(
                res_id
            )._get_and_set_external_taxes_on_eligible_records()

        return super().default_get(fields)
