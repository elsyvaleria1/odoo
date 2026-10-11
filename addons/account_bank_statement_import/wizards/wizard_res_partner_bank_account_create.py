from odoo import models


class WizardResPartnerBankAccountCreate(models.TransientModel):
    _inherit = "wizard.res.partner.bank.account.create"

    def action_finish_bank_setup(self):
        res = super().action_finish_bank_setup()
        if (self.linked_journal_id.bank_statements_source == "undefined") and self.env[
            "account.journal"
        ]._get_bank_statements_available_import_formats():
            self.linked_journal_id.bank_statements_source = "file_import"
        return res
