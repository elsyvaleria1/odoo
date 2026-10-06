from odoo import models
from odoo.tools.authority_keys import declare_authority_keys

declare_authority_keys("accountant", "skip_account_review_check")


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_in_payment_state(self) -> str:
        # OVERRIDE to enable the 'in_payment' state on invoices.
        return "in_payment"

    def _is_user_able_to_review(self) -> bool:
        # OVERRIDE of account, whose base returns a bool. Without the bool() a
        # truthy non-bool left in the context comes straight back out, and the
        # predicate stops answering the question it is named for.
        return bool(
            self.env.context.get("skip_account_review_check")
            or self.env.user.has_group("account.group_account_user")
        )
