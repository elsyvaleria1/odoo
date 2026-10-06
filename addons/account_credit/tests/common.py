from odoo.exceptions import RedirectWarning

AUTHORIZATION = "wizard.sale.order.confirm.credit.override"


class CreditAuthorizationCase:
    def _credit_authorization_action(self, orders):
        with self.assertRaises(RedirectWarning) as raised:
            orders.action_confirm()
        action = raised.exception.args[1]
        self.assertEqual(action["res_model"], AUTHORIZATION)
        return action

    def _credit_authorization_wizard(self, orders):
        action = self._credit_authorization_action(orders)
        return orders.env[AUTHORIZATION].with_context(**action["context"]).create({})


def book_payment_entries(env):
    chart = env["account.chart.template"]
    banks = env["account.journal"].search(
        [("type", "=", "bank"), ("company_id", "=", env.company.id)]
    )
    banks.inbound_payment_channel_ids.payment_account_id = chart.ref(
        "account_journal_payment_debit_account_id"
    )
    banks.outbound_payment_channel_ids.payment_account_id = chart.ref(
        "account_journal_payment_credit_account_id"
    )
