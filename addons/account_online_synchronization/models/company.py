from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def setting_init_bank_account_action(self):
        return self.env["account.online.link"].action_new_synchronization(
            journal_type="bank"
        )

    @api.model
    def setting_init_credit_card_account_action(self):
        return self.env["account.online.link"].action_new_synchronization(
            journal_type="credit"
        )
