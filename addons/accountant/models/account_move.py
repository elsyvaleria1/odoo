from odoo import models
from odoo.tools.authority_keys import declare_authority_keys

declare_authority_keys("accountant", "skip_account_review_check")


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_in_payment_state(self) -> str:
        return "in_payment"

    def _is_user_able_to_review(self) -> bool:
        return bool(
            self.env.context.get("skip_account_review_check")
            or self.env.user.has_group("account.group_account_user")
        )
