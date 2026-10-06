from odoo import models


class AccountBatchPayment(models.Model):
    _inherit = "account.batch.payment"

    def action_view_batch_payment(self) -> dict:
        self.check_singleton()
        return {
            "name": self.env._("Batch Payment"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "view_id": self.env.ref("account_batch_payment.view_batch_payment_form").id,
            "res_model": self._name,
            "res_id": self.id,
            "context": {
                "create": False,
                "delete": False,
            },
            "target": "current",
        }

    def _get_amls_for_reconciliation(self, st_line) -> tuple:
        amls_to_create, has_exchange_diff = (
            self.payment_ids._get_amls_for_reconciliation(st_line)
        )
        return amls_to_create, has_exchange_diff
