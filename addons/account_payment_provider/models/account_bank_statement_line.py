import re

from odoo import models


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _get_partial_amounts(
        self, current_balance, move_line, open_amount_currency, open_balance
    ) -> dict | None:
        for payment in move_line.move_id.payment_ids:
            if (
                re.match(r"^iso20022.*|^sepa_ct$", payment.payment_method_code)
                or payment.transaction_id
            ):
                return None

        return super()._get_partial_amounts(
            current_balance, move_line, open_amount_currency, open_balance
        )
