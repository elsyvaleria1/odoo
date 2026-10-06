from odoo import models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _get_journal_dashboard_data_batched(self):
        dashboard_data = super()._get_journal_dashboard_data_batched()
        self._update_dashboard_data_count(
            dashboard_data,
            "account.payment",
            "num_sepa_ct_to_send",
            [
                ("payment_channel_id.code", "=", "sepa_ct"),
                ("state", "=", "in_process"),
                ("is_sent", "=", False),
                ("is_bank_matched", "=", False),
            ],
        )
        return dashboard_data

    def action_sepa_ct_to_send(self) -> dict:
        payment_channel = self.outbound_payment_channel_ids.filtered(
            lambda l: l.code == "sepa_ct"
        )
        list_view_id = self.env.ref(
            "account_batch_payment.view_account_payment_tree_inherit_account_batch_payment"
        ).id
        return {
            "name": self.env._("SEPA Credit Transfers to Send"),
            "type": "ir.actions.act_window",
            "view_mode": "list,form,graph",
            "res_model": "account.payment",
            "domain": [
                ("payment_channel_id.code", "=", "sepa_ct"),
                ("state", "=", "in_process"),
                ("is_sent", "=", False),
                ("is_bank_matched", "=", False),
            ],
            "views": [[list_view_id, "list"], [False, "form"], [False, "graph"]],
            "context": dict(
                self.env.context,
                search_default_journal_id=self.id,
                search_default_outbound_filter=True,
                default_payment_channel_id=payment_channel.id,
            ),
        }
