from datetime import datetime, time, timedelta
from typing import Self

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    # used to control the renewal flow based on the transaction state
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
                # tx state in cancel or error
                renewal_state = "cancel"
            tx.renewal_state = renewal_state

    ####################
    # Business Methods #
    ####################

    def _prepare_mandate_data(self):
        """Override of `payment` to inject subscription-specific data into the mandate values.

        Note: `self.check_singleton()`

        :return: The dict of module-specific mandate values.
        :rtype: dict
        """
        mandate_values = super()._prepare_mandate_data()
        if len(self.sale_order_ids) != 1 or not self.sale_order_ids.is_subscription:
            return mandate_values

        # Convert start and end dates into datetime by setting the time to midnight.
        # Payment providers require the start_datetime of the mandate to not be lesser than yesterday
        # e.g., stripe: https://docs.stripe.com/api/payment_intents/create#create_payment_intent-payment_method_options-card-mandate_options-start_date
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
                # The maximum amount that can be charged with the mandated.
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
            # tx should be in an authorized renewal_state otherwise _reconcile_after_done will not be called
            # but this is a safety to prevent issue when the code is called manually
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
        # create the invoices for the transactions that are not yet linked to invoice
        # `_do_payment` do link an invoice to the payment transaction
        # calling `super()._invoice_sale_orders()` would create a second invoice for the next period
        # instead of the current period and would reconcile the payment with the new invoice
        def _filter_invoiced_subscription(self):
            self.check_singleton()
            # we look for tx with one invoice
            if len(self.invoice_ids) != 1:
                return False
            return any(
                self.invoice_ids.mapped(
                    "invoice_line_ids.sale_line_ids.order_id.is_subscription"
                )
            )

        return self.filtered(_filter_invoiced_subscription)

    def _get_partial_payment_subscription_transaction(self):
        # filter transaction which are only a partial payment of subscription and that don't fulfill a payment that
        # is already existing
        tx_with_partial_payments = self.env["payment.transaction"]
        for tx in self:
            order = tx.sale_order_ids.filtered(lambda so: so.state == "done")
            if not any(order.mapped("is_subscription")):
                # not subscription related
                continue
            if len(order) > 1:
                # we don't support multiple order per tx. Accounting should invoice manually
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
                # The payment amount and other unused transactions will confirm and pay the invoice
                tx_with_partial_payments |= tx
        return tx_with_partial_payments

    def _invoice_sale_orders(self):
        """Override of payment to increase next_invoice_date when needed."""
        transaction_to_invoice = self - self._get_invoiced_subscription_transaction()
        transaction_to_invoice -= self._get_partial_payment_subscription_transaction()
        # Update the next_invoice_date of SOL when the payment_mode is 'success_payment'
        # We have to do it here because when a client confirms and pay a SO from the portal with success_payment
        # The next_invoice_date won't be updated by the reconcile_pending_transaction callback (do_payment is not called)
        # Create invoice
        return super(PaymentTransaction, transaction_to_invoice)._invoice_sale_orders()

    def _post_process(self):
        """Override of `payment` to add Subscriptions-specific logic to the post-processing.

        In particular, for confirmed transactions we handle reconciliation for subscription's
        validation transaction references. For cancelled or error transactions, we call
        `_handle_unsuccessful_transaction`. If any subscription got paid, trigger the post
        subscription actions method in batch.

        :return: None
        """
        # Avoid post processing tx whose SO is still being processed by the invoice cron
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
                # Re-open churned subscriptions after payment.
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
        """
        Execute the subscription action once the transaction is in an acceptable state
        This will also reopen the order and remove the payment pending state.
        Partial payment should not have a subscription_action defined and therefore should not reopen the order.
        """
        reopen_reasons = self.env["sale.order.close.reason"]._get_reopen_reasons()
        for tx in self:
            orders = tx.sale_order_ids
            # quotation subscription paid on portal have pending transactions
            orders.pending_transaction = False
            if not tx.subscription_action or tx.renewal_state != "authorized":
                # We don't assign failing tokens, and we don't send emails
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
                # validation transaction have the `assign_token` `subscription_action`
                # Once the token is assigned, we are done because we don't send emails in that case.
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
        # we're going to send subscription invoices with a specific
        # email, so skip those from here to not send them a second time
        return super(PaymentTransaction, self - subscription_action_txs)._send_invoice()

    def _set_done(self, **kwargs):
        orders = self.sale_order_ids
        # Flag of subscription processed in the cron is removed in the cron to avoid concurrent updates
        orders.filtered(
            lambda so: so.is_subscription and not so.is_invoice_cron
        ).payment_exception = False
        return super()._set_done(**kwargs)

    def _set_pending(self, **kwargs):
        orders = self.sale_order_ids
        # Flag of subscription processed in the cron is removed in the cron to avoid concurrent updates
        orders.filtered(
            lambda so: so.is_subscription and not so.is_invoice_cron
        ).payment_exception = False
        return super()._set_pending(**kwargs)

    def _set_authorized(self, **kwargs):
        orders = self.sale_order_ids
        # Flag of subscription processed in the cron is removed in the cron to avoid concurrent updates
        orders.filtered(
            lambda so: so.is_subscription and not so.is_invoice_cron
        ).payment_exception = False
        return super()._set_authorized(**kwargs)

    def _handle_unsuccessful_transaction(self) -> None:
        """Unset pending transactions for subscriptions and cancel their draft invoices."""
        for transaction in self:
            subscriptions = transaction.sale_order_ids.filtered("is_subscription")
            if subscriptions:
                # Flag of subscription processed in the cron is removed in the cron to avoid concurrent updates
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
        """Cancel draft invoices attached to subscriptions."""
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
        """Override `payment` to filter out invoices whose logging is already handled by the cron.

        This prevents deadlocks from happening in the case where:
        1. the cron creates invoices linked to the transaction;
        2. initiate the payment;
        3. commits the cursor;
        4. deletes the linked invoices because the payment didn't go through;
        5. the payment webhook tries to log the payment failure on the committed-but-now-deleted
           invoices.
        """
        return self.invoice_ids.filtered(
            lambda invoice: (
                not any(
                    o.is_invoice_cron
                    for o in invoice.invoice_line_ids.sale_line_ids.order_id
                )
            )
        )
