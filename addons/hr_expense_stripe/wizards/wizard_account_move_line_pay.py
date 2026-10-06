from odoo import models


class WizardAccountMoveLinePay(models.TransientModel):
    _name = "wizard.account.move.line.pay"
    _inherit = ["wizard.account.move.line.pay"]

    def _get_batch_available_journals(self, batch_result, company=None):
        # EXTEND account, filter out stripe issuing journals, as they are not used for making payments manually
        # This is to avoid confusion when selecting journals in the payment register
        journals = super()._get_batch_available_journals(batch_result, company=company)
        return journals.filtered(
            lambda jrnl: jrnl.bank_statements_source != "stripe_issuing"
        )
