from odoo import models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _is_eligible_for_stock_account(self) -> bool:
        self.check_singleton()
        return bool(
            super()._is_eligible_for_stock_account()
            and not any(sol.is_rental for sol in self.sale_line_ids)
        )
