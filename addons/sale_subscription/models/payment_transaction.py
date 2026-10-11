from datetime import datetime, time, timedelta
from typing import Self

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    renewal_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("pending", "Pending"),
            ("authorized", "Authorized"),
            ("cancel", "Refused"),
        ],
        compute="_compute_renewal_state",
    )
    subscription_action = fields.Selection(
        selection=[
            ("automatic_send_mail", "Send Mail (automatic payment)"),
            ("manual_send_mail", "Send Mail (manual payment)"),
            ("assign_token", "Assign Token"),
        ]
    )

    @api.depends("state")
    def _compute_renewal_state(self) -> None:
        for tx in self:
            if tx.state in ["draft", "pending"]:
                renewal_state = tx.state
            elif tx.state in ("done", "authorized"):
                renewal_state = "authorized"
            else:
                renewal_state = "cancel"
            tx.renewal_state = renewal_state


    def _prepare_mandate_data(self):
        mandate_values = super()._prepare_mandate_data()
        if len(self.sale_order_ids) != 1 or not self.sale_order_ids.is_subscription:
            return mandate_values

        current_time = fields.Datetime.now()
        start_date = self.sale_order_ids.start_date or current_time
        start_datetime = max(
            datetime.combine(start_date, time()), current_time - timedelta(days=1)
        )
        end_datetime = self.sale_order_ids.end_date and datetime.combine(
            self.sale_order_ids.end_date, time()
        )
        mandate_values.update(
            {
                "amount": self.sale_order_ids.amount_total,
                "MRR": self.sale_order_ids.recurring_monthly,
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "recurrence_unit": self.sale_order_ids.plan_id.repeat_unit,
                "recurrence_duration": self.sale_order_ids.plan_id.repeat_interval,
            }
        )
        return mandate_values

    def _create_or_link_to_invoice(self) -> None:
        self.check_singleton()
        if (
            len(self.sale_order_ids) > 1
            or self.invoice_ids
            or not self.sale_order_ids.is_subscription
        ):
            return
        elif self.renewal_state in ["draft", "pending", "cancel"]:
            return
        self._cancel_draft_invoices()
        self._invoice_sale_orders()
        invoices = self.invoice_ids.with_company(self.company_id)
        with invoices._exempting_posting_from_approval("payment_received"):
            invoices._post()
        self.invoice_ids.write({"matched_payment_ids": self.payment_id.ids})
        if not self.subscription_action and not self.env.context.get(
            "skip_sale_auto_invoice_send"
        ):
            self.invoice_ids.transaction_ids._send_invoice()

    def _get_invoiced_subscription_transaction(self) -> Self:
        def _filter_invoiced_subscription(self):
            self.check_singleton()
            if len(self.invoice_ids) != 1:
                return False
            return any(
                self.invoice_ids.mapped(
                    "invoice_line_ids.sale_line_ids.order_id.is_subscription"
                )
            )

        return self.filtered(_filter_invoiced_subscription)

    def _get_partial_payment_subscription_transaction(self):
        tx_with_partial_payments = self.env["payment.transaction"]
        for tx in self:
            order = tx.sale_order_ids.filtered(lambda so: so.state == "done")
            if not any(order.mapped("is_subscription")):
                continue
            if len(order) > 1:
                tx_with_partial_payments |= tx
                continue
            expected_amount = (
                order._next_billing_details()["tax_totals"]["total_amount_currency"]
                if len(order._get_invoiced_subscriptions()) == 0
                else order._next_billing_details()["next_invoice_amount"]
            )
            if (
                order.currency_id.compare_amounts(
                    sum(
                        order.transaction_ids.filtered(
                            lambda tx: (
                                tx.renewal_state == "authorized" and not tx.invoice_ids
                            )
                        ).mapped("amount")
                    ),
                    expected_amount,
                )
                != 0
            ):
                tx_with_partial_payments |= tx
        return tx_with_partial_payments

    def _invoice_sale_orders(self):
        transaction_to_invoice = self - self._get_invoiced_subscription_transaction()
        transaction_to_invoice -= self._get_partial_payment_subscription_transaction()
        return super(PaymentTransaction, transaction_to_invoice)._invoice_sale_orders()

    def _post_process(self):
        process_tx = self.filtered(
            lambda tx: not any(tx.sale_order_ids.mapped("is_invoice_cron"))
        )
        _debug.pipeline(
            "subscription_tx_post_process",
            transactions=self,
            processed=process_tx,
            skipped_in_cron=self - process_tx,
        )
        res = super(PaymentTransaction, process_tx)._post_process()
        any_paid_subscription = False
        reopen_reasons = self.env["sale.order.close.reason"]._get_reopen_reasons()
        for tx in process_tx:
            orders = tx.sale_order_ids or tx.invoice_ids.line_ids.subscription_id
            subscriptions = orders.filtered(lambda order: order.is_subscription)
            if tx.state == "done" and len(subscriptions) > 0:
                if tx.operation != "validation":
                    tx.with_context(forced_invoice=True)._create_or_link_to_invoice()
                any_paid_subscription = True
                subscriptions._filtered_reopenable(
                    tx.last_state_change.date(), reopen_reasons
                ).set_open()
                _debug.lifecycle(
                    "subscription_paid", transaction=tx, subscriptions=subscriptions
                )
            elif tx.state in ("error", "cancel"):
                _debug.logic(
                    "subscription_tx_unsuccessful", transaction=tx, state=tx.state
                )
                tx._handle_unsuccessful_transaction()
        if any_paid_subscription:
            self._post_subscription_action()
        return res

    def _post_subscription_action(self) -> None:
        reopen_reasons = self.env["sale.order.close.reason"]._get_reopen_reasons()
        for tx in self:
            orders = tx.sale_order_ids
            orders.pending_transaction = False
            if not tx.subscription_action or tx.renewal_state != "authorized":
                _debug.logic(
                    "subscription_action_skipped",
                    transaction=tx,
                    action=tx.subscription_action or "none",
                    renewal_state=tx.renewal_state,
                )
                continue
            if tx.subscription_action == "assign_token":
                _debug.lifecycle(
                    "payment_token_assigned", transaction=tx, orders=orders
                )
                orders._update_token(tx)
            if tx.operation == "validation":
                continue
            orders.filtered(
                lambda order: (
                    order.subscription_state != "6_churn"
                    or not order.close_reason_id
                    or order.close_reason_id in reopen_reasons
                )
            ).set_open()
            if tx.subscription_action:
                automatic = tx.subscription_action == "automatic_send_mail"
                for order in orders:
                    _debug.pipeline(
                        "subscription_payment_success",
                        order=order,
                        transaction=tx,
                        automatic=automatic,
                    )
                    order._subscription_post_success_payment(
                        tx, tx.invoice_ids, automatic=automatic
                    )

    def _send_invoice(self):
        subscription_action_txs = self.filtered(
            lambda tx: (
                tx.operation != "validation"
                and tx.subscription_action
                and tx.renewal_state == "authorized"
                and not tx.is_post_processed
            )
        )
        return super(PaymentTransaction, self - subscription_action_txs)._send_invoice()

    def _set_done(self, **kwargs):
        orders = self.sale_order_ids
        orders.filtered(
            lambda so: so.is_subscription and not so.is_invoice_cron
        ).payment_exception = False
        return super()._set_done(**kwargs)

    def _set_pending(self, **kwargs):
        orders = self.sale_order_ids
        orders.filtered(
            lambda so: so.is_subscription and not so.is_invoice_cron
        ).payment_exception = False
        return super()._set_pending(**kwargs)

    def _set_authorized(self, **kwargs):
        orders = self.sale_order_ids
        orders.filtered(
            lambda so: so.is_subscription and not so.is_invoice_cron
        ).payment_exception = False
        return super()._set_authorized(**kwargs)

    def _handle_unsuccessful_transaction(self) -> None:
        for transaction in self:
            subscriptions = transaction.sale_order_ids.filtered("is_subscription")
            if subscriptions:
                _debug.lifecycle(
                    "subscription_payment_unwound",
                    transaction=transaction,
                    subscriptions=subscriptions,
                )
                subscriptions.filtered(
                    lambda so: not so.is_invoice_cron
                ).pending_transaction = False
                transaction._cancel_draft_invoices()

    def _cancel_draft_invoices(self) -> None:
        self.check_singleton()
        subscriptions = self.sale_order_ids.filtered("is_subscription")
        draft_invoices = subscriptions.line_ids.invoice_line_ids.move_id.filtered(
            lambda am: am.state == "draft"
        )
        if draft_invoices:
            _debug.lifecycle(
                "draft_invoices_cancelled", transaction=self, invoices=draft_invoices
            )
            draft_invoices.action_cancel()

    def _get_invoices_to_notify(self):
        return self.invoice_ids.filtered(
            lambda invoice: (
                not any(
                    o.is_invoice_cron
                    for o in invoice.invoice_line_ids.sale_line_ids.order_id
                )
            )
        )
