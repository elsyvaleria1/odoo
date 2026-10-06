from odoo import models
from odoo.exceptions import UserError

from odoo.addons.hr_expense_stripe.utils import (
    format_amount_to_stripe,
    send_request_stripe_proxy,
)


class WizardAccountJournalTopup(models.TransientModel):
    _inherit = "wizard.account.journal.topup"

    def action_simulate_topup(self) -> None:
        """Test-mode push only, send the topup simulation request to stripe so we can test payments without going to stripe dashboard"""
        self.check_singleton()

        if self.is_live_mode or self.pull_push_funds == "pull":
            raise UserError(
                self.env._(
                    "The indirect top-up simulation isn't available in your country."
                )
            )

        payload = {
            "account": self.sudo().company_id.stripe_id,
            "amount": format_amount_to_stripe(self.amount, self.currency_id),
            "currency": self.currency_id.name,
        }

        send_request_stripe_proxy(
            self.company_id.sudo(),
            "test_helpers/fund_balance",
            payload=payload,
            method="POST",
        )
