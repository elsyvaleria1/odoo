import time

from odoo import SUPERUSER_ID, api, fields, models, modules, tools
from odoo.exceptions import UserError, ValidationError

STATEMENT_LINE_CREATION_BATCH_SIZE = 500


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    online_transaction_identifier = fields.Char(readonly=True)
    online_partner_information = fields.Char(readonly=True)
    online_account_id = fields.Many2one(
        comodel_name="account.online.account",
        readonly=True,
    )
    online_link_id = fields.Many2one(
        comodel_name="account.online.link",
        related="online_account_id.account_online_link_id",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        bank_statement_lines = super().create(vals_list)
        moves_to_cancel = self.env["account.move"]
        for bank_statement_line in bank_statement_lines:
            transaction_details = bank_statement_line.transaction_details or {}
            if not transaction_details.get("is_zero_balancing"):
                continue
            moves_to_cancel |= bank_statement_line.move_id
        moves_to_cancel.action_cancel()

        return bank_statement_lines

    @api.model
    def _online_sync_bank_statement(self, transactions, online_account):
        start_time = time.time()
        lines_to_reconcile = self.env["account.bank.statement.line"]
        try:
            for journal in online_account.journal_ids:
                journal.sudo().write({"bank_statements_source": "online_sync"})
                if not transactions:
                    continue

                sorted_transactions = sorted(
                    transactions, key=lambda transaction: transaction["date"]
                )
                total = self.env.context.get("transactions_total") or sum(
                    transaction["amount"] for transaction in transactions
                )
                any_st_line = self.search_count(
                    [("journal_id", "=", journal.id)], limit=1
                )
                journal_currency = journal.currency_id or journal.company_id.currency_id
                start_balance = online_account.balance - total
                if not any_st_line and not journal_currency.is_zero(start_balance):
                    lines_to_reconcile = self.with_context(
                        skip_statement_line_cron_trigger=True
                    ).create(sorted_transactions[0])
                    self.env["account.bank.statement"].create(
                        {
                            "journal_id": journal.id,
                            "date": lines_to_reconcile.date,
                            "balance_start": start_balance,
                            "balance_end_real": start_balance
                            + lines_to_reconcile.amount,
                            "line_ids": lines_to_reconcile,
                            "name": self.env._(
                                "Opening Statement: First Synchronization"
                            ),
                        }
                    )

                filtered_transactions = online_account._get_filtered_transactions(
                    sorted_transactions
                )

                do_commit = not modules.module.current_test
                if filtered_transactions:
                    for index in range(
                        0,
                        len(filtered_transactions),
                        STATEMENT_LINE_CREATION_BATCH_SIZE,
                    ):
                        lines_to_reconcile += (
                            self.with_user(SUPERUSER_ID)
                            .with_company(journal.company_id)
                            .with_context(skip_statement_line_cron_trigger=True)
                            .create(
                                filtered_transactions[
                                    index : index + STATEMENT_LINE_CREATION_BATCH_SIZE
                                ]
                            )
                        )
                        if do_commit:
                            self.env["ir.cron"]._commit_progress()
                    journal.account_online_account_id.sudo().write(
                        {"last_sync": filtered_transactions[-1]["date"]}
                    )

                if lines_to_reconcile:
                    if len(lines_to_reconcile) <= 80:
                        lines_to_reconcile._try_auto_reconcile_statement_lines()
                    else:
                        cron_limit_time = tools.config["limit_time_real_cron"] or -1
                        limit_time = (
                            cron_limit_time if cron_limit_time > 0 else 180
                        ) - (time.time() - start_time)
                        if limit_time > 0:
                            lines_to_reconcile._cron_try_auto_reconcile_statement_lines(
                                batch_size=100, limit_time=limit_time
                            )

        except (UserError, ValidationError) as e:
            link = online_account.account_online_link_id
            subject = self.env._("Error")
            link._log_information("error", subject=subject, message=str(e))
            link._replay_on_rollback("_log_information", "error", subject, str(e))
            raise
        return lines_to_reconcile
