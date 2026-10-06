from odoo import fields, models


class WizardResPartnerUpdateAddress(models.TransientModel):
    _inherit = "wizard.res.partner.update.address"

    def action_save_validated(self):
        res = super().action_save_validated()
        for wizard in self:
            wizard.partner_id.write(
                {
                    "date_localization": fields.Date.context_today(wizard.partner_id),
                    "is_avatax_valid": True,
                }
            )
        return res
