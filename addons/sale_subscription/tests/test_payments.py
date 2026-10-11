import datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common_posting_obligation import (
    exemption_notes,
    holding_invoice_posting,
)
from odoo.addons.mail.tests.common import MockEmail
from odoo.addons.payment.tests.common import PaymentCommon
from odoo.addons.sale_subscription.tests.common_sale_subscription import (
    TestSubscriptionCommon,
)


@tagged("post_install", "-at_install")
class TestSubscriptionPayments(PaymentCommon, TestSubscriptionCommon, MockEmail):
    def _get_payment_values(
        self, subscription, invoice_ids, amount=None, reference="PAYMENT"
    ):
        return {
            "amount": amount or subscription.amount_total,
            "provider_id": self.provider.id,
            "payment_method_id": self.payment_method_id,
            "operation": "offline",
            "currency_id": subscription.currency_id.id,
            "reference": reference,
            "token_id": False,
            "partner_id": subscription.partner_id.id,
            "partner_country_id": subscription.partner_id.country_id.id,
            "invoice_ids": invoice_ids,
            "sale_order_ids": [(6, 0, subscription.ids)],
            "state": "draft",
        }

    def test_auto_payment_with_token(self):

        self.original_prepare_invoice = self.subscription._prepare_invoice_vals

        with patch(
            "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
            wraps=self._mock_subscription_do_payment,
        ):
            self.subscription.write(
                {
                    "partner_id": self.partner.id,
                    "company_id": self.company.id,
                    "payment_token_id": self.payment_token.id,
                    "template_id": self.subscription_tmpl.id,
                }
            )
            self.subscription._onchange_template_id()
            self.subscription.action_confirm()
            self.env["sale.order"]._cron_recurring_create_invoice()
            self.subscription.transaction_ids._post_process()
            self.assertEqual(
                self.subscription.subscription_state,
                "3_progress",
                "subscription with online payment and a payment method set should stay opened when transaction succeeds",
            )
            invoice = self.subscription.invoice_ids.sorted("date")[-1]
            recurring_total_with_taxes = self.subscription.amount_total
            self.assertEqual(
                invoice.amount_total,
                recurring_total_with_taxes,
                "website_subscription: the total of the recurring invoice created should be the subscription "
                "recurring total + the products taxes",
            )
            self.assertTrue(
                all(
                    line.tax_ids.ids == self.tax_10.ids
                    for line in invoice.invoice_line_ids
                ),
                "website_subscription: All lines of the recurring invoice created should have the percent tax "
                "set on the subscription products",
            )
            self.assertTrue(
                all(
                    tax_line.tax_line_id == self.tax_10
                    for tax_line in invoice.line_ids.filtered("tax_line_id")
                ),
                "The invoice tax lines should be set and should all use the tax set on the subscription products",
            )

            start_date = fields.Date.today() - relativedelta(months=1)
            recurring_next_date = fields.Date.today() - relativedelta(days=1)
            self.subscription.payment_token_id = False
            failing_subs = self.env["sale.order"]
            subscription_mail_fail = self.subscription.copy(
                {
                    "date_order": start_date,
                    "start_date": start_date,
                    "next_invoice_date": recurring_next_date,
                    "payment_token_id": None,
                }
            )

            failing_subs |= subscription_mail_fail
            for _i in range(5):
                failing_subs |= subscription_mail_fail.copy({"is_batch": True})
            failing_subs.action_confirm()
            failing_subs.line_ids.qty_to_invoice = 1
            self.env["sale.order"]._create_recurring_invoice(batch_size=3)
            failing_result = [
                not res for res in failing_subs.mapped("payment_exception")
            ]
            self.assertTrue(
                all(failing_result), "The subscription are not flagged anymore"
            )
            failing_result = [not res for res in failing_subs.mapped("is_batch")]
            self.assertTrue(
                all(failing_result), "The subscription are not flagged anymore"
            )
            failing_subs.payment_token_id = self.payment_token.id
            failing_subs._create_recurring_invoice()
            vals = [
                sub.payment_exception for sub in failing_subs if sub.payment_exception
            ]
            self.assertFalse(
                vals, "The subscriptions are not flagged anymore, the payment succeeded"
            )

    def test_a_charged_renewal_invoice_does_not_wait_for_approval(self):
        self.original_prepare_invoice = self.subscription._prepare_invoice_vals
        self.subscription.write(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "payment_token_id": self.payment_token.id,
                "template_id": self.subscription_tmpl.id,
            }
        )
        self.subscription._onchange_template_id()
        self.subscription.action_confirm()

        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=self._mock_subscription_do_payment,
            ),
            holding_invoice_posting(self.env),
        ):
            self.env["sale.order"]._cron_recurring_create_invoice()
            self.subscription.transaction_ids._post_process()

        invoice = self.subscription.invoice_ids
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(len(exemption_notes(invoice, "payment_received")), 1)

    def test_auto_payment_across_time(self):
        self.original_prepare_invoice = self.subscription._prepare_invoice_vals

        with patch(
            "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
            wraps=self._mock_subscription_do_payment,
        ):
            subscription_tmpl = self.env["sale.order.template"].create(
                {
                    "name": "Subscription template without discount",
                    "is_unlimited": False,
                    "note": "This is the template description",
                    "duration_value": 4,
                    "duration_unit": "month",
                    "plan_id": self.plan_month.id,
                }
            )

            self.subscription.write(
                {
                    "partner_id": self.partner.id,
                    "company_id": self.company.id,
                    "payment_token_id": self.payment_token.id,
                    "template_id": subscription_tmpl.id,
                }
            )
            self.subscription._onchange_template_id()
            with freeze_time("2021-01-03"):
                self.subscription.line_ids = [Command.clear()]
                self.subscription.write(
                    {
                        "start_date": False,
                        "next_invoice_date": False,
                        "line_ids": [
                            Command.create(
                                {
                                    "product_id": self.product.id,
                                    "name": "month cheap",
                                    "price_unit": 42,
                                    "product_qty": 2,
                                }
                            ),
                            Command.create(
                                {
                                    "product_id": self.product2.id,
                                    "name": "month expensive",
                                    "price_unit": 420,
                                    "product_qty": 3,
                                }
                            ),
                        ],
                    }
                )
                self.subscription.action_confirm()
                self.assertEqual(self.subscription.end_date, datetime.date(2021, 5, 2))
                self.env["sale.order"]._cron_recurring_create_invoice()
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                tx = self.env["payment.transaction"].search(
                    [("invoice_ids", "in", invoice.ids)]
                )
                tx._post_process()
                self.assertEqual(
                    len(invoice.invoice_line_ids), 2, "Two lines are invoiced"
                )
                self.assertEqual(
                    self.subscription.next_invoice_date,
                    datetime.date(2021, 2, 3),
                    "the next invoice date should be updated",
                )
                self.assertEqual(
                    invoice.invoice_line_ids[0].name,
                    "BaseTestProduct\nmonth cheap\n1 Month 01/03/2021 to 02/02/2021",
                    "Invoice line description must be based on order line description",
                )
                self.assertEqual(
                    invoice.invoice_line_ids[1].name,
                    "TestProduct2\nmonth expensive\n1 Month 01/03/2021 to 02/02/2021",
                    "Invoice line description must be based on order line description",
                )

            with freeze_time("2021-02-03"):
                self.env.invalidate_all()
                self.env["sale.order"]._cron_recurring_create_invoice()
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                tx = self.env["payment.transaction"].search(
                    [("invoice_ids", "in", invoice.ids)]
                )
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                self.assertEqual(
                    invoice.date, datetime.date(2021, 2, 3), "We invoiced today"
                )
                tx._post_process()

            with freeze_time("2021-03-03"):
                self.env.invalidate_all()
                self.env["sale.order"]._cron_recurring_create_invoice()
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                tx = self.env["payment.transaction"].search(
                    [("invoice_ids", "in", invoice.ids)]
                )
                tx._post_process()
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                self.assertEqual(
                    invoice.date, datetime.date(2021, 3, 3), "We invoiced today"
                )

            with freeze_time("2021-04-03"):
                self.subscription.invalidate_recordset()
                self.env["sale.order"]._cron_recurring_create_invoice()
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                tx = self.env["payment.transaction"].search(
                    [("invoice_ids", "in", invoice.ids)]
                )
                tx._post_process()
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                tx = self.env["payment.transaction"].search(
                    [("invoice_ids", "in", invoice.ids)]
                )
                tx._post_process()
                self.assertEqual(
                    invoice.date, datetime.date(2021, 4, 3), "We invoiced today"
                )

            with freeze_time("2022-05-03"):
                self.subscription.invalidate_recordset(fnames=["subscription_state"])
                self.env["sale.order"]._cron_recurring_create_invoice()
                self.assertEqual(
                    self.subscription.subscription_state,
                    "6_churn",
                    "the end_date is passed, the subscription is automatically closed",
                )
                invoice = self.subscription.invoice_ids.sorted("date")[-1]
                self.assertEqual(
                    invoice.date,
                    datetime.date(2021, 4, 3),
                    "We should not create a new invoices",
                )

    def test_do_payment_calls_send_payment_request_only_once(self):
        self.invoice = self.env["account.move"].create(
            self.subscription._prepare_invoice_vals()
        )
        with patch(
            "odoo.addons.payment.models.payment_transaction.PaymentTransaction"
            "._charge_with_token"
        ) as patched:
            self.subscription._do_payment(self._create_token(), self.invoice)
            patched.assert_called_once()

    def test_payment_token_is_saved(self):
        portal_partner = self.user_portal.partner_id
        success_payment_template_id = self.subscription_tmpl.copy()
        subscription = self.env["sale.order"].create(
            {
                "partner_id": portal_partner.id,
                "template_id": success_payment_template_id.id,
            }
        )
        subscription._onchange_template_id()
        subscription.action_quotation_sent()

        test_payment_token = (
            self.env["payment.token"]
            .sudo()
            .create(
                {
                    "payment_details": "Test",
                    "partner_id": portal_partner.id,
                    "provider_id": self.dummy_provider.id,
                    "payment_method_id": self.payment_method_id,
                    "provider_ref": "test",
                }
            )
        )
        payment_with_token = self.env["account.payment"].create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "amount": subscription.amount_total,
                "date": subscription.date_order,
                "currency_id": subscription.currency_id.id,
                "partner_id": portal_partner.id,
                "payment_token_id": test_payment_token.id,
            }
        )

        transaction_ids = payment_with_token._create_payment_transaction()
        transaction_ids._set_done()

        subscription.write({"transaction_ids": [(6, 0, transaction_ids.ids)]})
        subscription.action_confirm()

        self.assertTrue(subscription.is_subscription)
        self.assertEqual(subscription.payment_token_id.id, test_payment_token.id)

    @mute_logger("odoo.addons.sale_subscription.models.sale_order")
    def test_exception_mail(self):
        self.subscription.write(
            {
                "payment_token_id": self.payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        self.subscription.action_confirm()
        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                side_effect=Exception("Bad Token"),
            ),
            self.mock_mail_gateway(),
        ):
            self.subscription._create_recurring_invoice()
        found_mail = self._find_mail_mail_wemail(
            "accountman@test.com", "sent", author=self.env.user.partner_id
        )
        mail_body = (
            "<p>Error during renewal of contract [%s] Customer REF XXXXXXX Payment not recorded</p><p>Bad Token</p>"
            % self.subscription.id
        )
        self.assertEqual(found_mail.body_html, mail_body)

    @mute_logger("odoo.addons.sale_subscription.models.sale_order")
    def test_bad_payment_exception(self):
        self.subscription.write(
            {
                "payment_token_id": self.payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        self.subscription.action_confirm()

        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                side_effect=Exception("Oops, network error"),
            ),
            self.mock_mail_gateway(),
        ):
            self.subscription._create_recurring_invoice()

        invoice = self.subscription.line_ids.invoice_line_ids.move_id
        self.assertFalse(
            invoice,
            "The draft invoice should be deleted when something goes wrong in _handle_automatic_invoices",
        )
        self.assertEqual(
            self.subscription.next_invoice_date,
            self.subscription.start_date,
            "We should not have updated the next invoice date, as the invoice was unlinked",
        )

    @mute_logger("odoo.addons.sale_subscription.models.sale_order")
    def test_bad_payment_exception_post_success(self):
        self.subscription.write(
            {
                "payment_token_id": self.payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        self.subscription.action_confirm()

        def _mock_subscription_do_payment_and_commit(
            payment_method, invoice, auto_commit=False
        ):
            tx = self._mock_subscription_do_payment(
                payment_method, invoice, auto_commit=auto_commit
            )
            tx.env.cr.flush()
            return tx

        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=_mock_subscription_do_payment_and_commit,
            ),
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._subscription_post_success_payment",
                side_effect=RuntimeError("Kaput"),
            ),
            self.mock_mail_gateway(),
        ):
            invoice = self.subscription._create_recurring_invoice()
            with self.assertRaisesRegex(RuntimeError, "Kaput"):
                invoice.transaction_ids._post_process()

        invoice = self.subscription.line_ids.invoice_line_ids.move_id
        self.assertTrue(
            invoice and invoice.state == "posted",
            "The draft invoice has to be kept as we committed after the payment succeeded "
            "(the next invoice date has already been updated).",
        )
        expected_next_invoice_date = (
            self.subscription.start_date + self.subscription.plan_id.billing_period
        )
        self.assertEqual(
            self.subscription.next_invoice_date,
            expected_next_invoice_date,
            "The next invoice date should have been updated, as the invoice was kept after the payment succeeded",
        )

    @mute_logger("odoo.addons.sale_subscription.models.sale_order")
    def test_a_captured_payment_keeps_its_invoice_when_posting_fails(self):
        self.subscription.write(
            {
                "payment_token_id": self.payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        self.subscription.action_confirm()
        invoice = self.subscription._create_invoices()
        self.assertEqual(invoice.state, "draft")

        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=self._mock_subscription_do_payment,
            ),
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._subscription_commit_cursor",
                side_effect=Exception("Commit failed"),
            ),
            self.mock_mail_gateway(),
        ):
            self.subscription._handle_automatic_invoices(invoice, auto_commit=False)

        self.assertTrue(invoice.exists())
        self.assertEqual(invoice.state, "draft")
        self.assertEqual(invoice.transaction_ids.renewal_state, "authorized")

    @mute_logger("odoo.addons.sale_subscription.models.sale_order")
    def test_bad_payment_rejected(self):
        self.subscription.write(
            {
                "payment_token_id": self.payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        self.subscription.action_confirm()

        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=self._mock_subscription_do_payment_rejected,
            ),
            self.mock_mail_gateway(),
        ):
            self.subscription._create_recurring_invoice()

        invoice = self.subscription.line_ids.invoice_line_ids.move_id
        self.assertFalse(
            self.subscription.pending_transaction,
            "The pending transaction flag should not remain",
        )
        self.assertFalse(
            invoice,
            "The draft invoice should be deleted when something goes wrong in _handle_automatic_invoices",
        )
        self.assertEqual(
            self.subscription.next_invoice_date,
            self.subscription.start_date,
            "We should not have updated the next invoice date, as the invoice was unlinked",
        )

    def test_manual_invoice_with_token(self):
        self.subscription.write(
            {
                "payment_token_id": self.payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        with freeze_time("2021-01-03"):
            self.subscription.action_confirm()
            self.subscription._create_invoices()
            self.subscription.line_ids.invoice_line_ids.move_id._post()
            self.assertEqual(
                self.subscription.next_invoice_date,
                datetime.date(2021, 2, 3),
                "the next invoice date should be updated",
            )
            self.assertEqual(self.subscription.invoice_count, 1)

    def test_close_unpaid_contracts(self):
        with freeze_time("2022-01-01"):
            sub0 = self.env["sale.order"].create(
                {
                    "name": "Paid",
                    "partner_id": self.partner.id,
                    "payment_term_id": self.env.ref(
                        "payment_term.account_payment_term_21days"
                    ).id,
                    "template_id": self.templ_5_days.id,
                }
            )
            sub0._onchange_template_id()
            sub0.action_confirm()
            sub1 = sub0.copy(default={"name": "Unpaid with simple date"})
            sub2 = sub1.copy(
                default={
                    "name": "Partial",
                    "payment_term_id": self.env.ref(
                        "payment_term.account_payment_term_advance_60days"
                    ).id,
                }
            )
            sub2.template_id = self.templ_60_days.id
            sub3 = sub1.copy(
                default={
                    "name": "Unpaid",
                    "payment_term_id": self.env.ref(
                        "payment_term.account_payment_term_advance_60days"
                    ).id,
                }
            )
            sub4 = self.env["sale.order"].create(
                {
                    "name": "Contract without template",
                    "is_subscription": True,
                    "plan_id": self.plan_year.id,
                    "partner_id": self.user_portal.partner_id.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": self.product.name,
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": self.product2.name,
                                "product_id": self.product2.id,
                                "product_qty": 1.0,
                            },
                        ),
                    ],
                }
            )
            all_subs = (sub1 | sub2 | sub3 | sub4).sorted("id")
            all_subs.origin_order_id = False
            for sub in all_subs - sub4:
                sub._onchange_template_id()
            all_subs.action_confirm()
            self.env["sale.order"]._cron_recurring_create_invoice()
            account_moves = (
                sub1.invoice_ids
                | sub2.invoice_ids
                | sub3.invoice_ids
                | sub4.invoice_ids
            )

        with freeze_time("2022-02-01"):
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=sub1.invoice_ids.ids
            ).create(
                {
                    "currency_id": sub1.currency_id.id,
                    "amount": 50,
                }
            )._create_payments()
            self.assertEqual(sub1.invoice_ids.payment_state, "partial")
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=sub0.invoice_ids.ids
            ).create(
                {
                    "currency_id": sub0.currency_id.id,
                    "amount": 400,
                }
            )._create_payments()

            self.assertTrue(sub0.invoice_ids.payment_state in ["in_payment", "paid"])
            self.assertEqual(
                account_moves.mapped("payment_state"),
                ["partial", "not_paid", "not_paid", "not_paid"],
            )
            template_limit = {
                account_moves[0].id: 5,
                account_moves[1].id: 60,
                account_moves[2].id: 5,
                account_moves[3].id: 15,
            }
            date_data = [
                (
                    aml.date_maturity,
                    aml.date_maturity
                    + relativedelta(days=template_limit[aml.move_id.id]),
                    aml.move_id.id,
                    aml.move_id.invoice_line_ids.sale_line_ids.order_id.name,
                )
                for aml in account_moves.line_ids.filtered("date_maturity")
            ]
            self.assertEqual(
                date_data,
                [
                    (
                        datetime.date(2022, 1, 22),
                        datetime.date(2022, 1, 27),
                        account_moves[0].id,
                        "Unpaid with simple date",
                    ),
                    (
                        datetime.date(2022, 1, 1),
                        datetime.date(2022, 3, 2),
                        account_moves[1].id,
                        "Partial",
                    ),
                    (
                        datetime.date(2022, 3, 2),
                        datetime.date(2022, 5, 1),
                        account_moves[1].id,
                        "Partial",
                    ),
                    (
                        datetime.date(2022, 1, 1),
                        datetime.date(2022, 1, 6),
                        account_moves[2].id,
                        "Unpaid",
                    ),
                    (
                        datetime.date(2022, 3, 2),
                        datetime.date(2022, 3, 7),
                        account_moves[2].id,
                        "Unpaid",
                    ),
                    (
                        datetime.date(2022, 1, 1),
                        datetime.date(2022, 1, 16),
                        account_moves[3].id,
                        "Contract without template",
                    ),
                ],
            )

        with freeze_time("2022-02-01"):
            self.env["sale.order"].sudo()._cron_subscription_expiration()
            self.assertEqual(
                all_subs.mapped("subscription_state"),
                ["3_progress", "3_progress", "3_progress", "6_churn"],
                "First and last invoices are never paid",
            )

        with freeze_time("2022-03-08"):
            self.env["sale.order"].sudo()._cron_subscription_expiration()
            self.assertEqual(
                all_subs.mapped("subscription_state"),
                ["3_progress", "3_progress", "6_churn", "6_churn"],
                "Unpaid payment expire on 2022-03-02 +  5days = 2022-03-07",
            )

        with freeze_time("2022-05-02"):
            self.env["sale.order"].sudo()._cron_subscription_expiration()
            self.assertEqual(
                account_moves.mapped("payment_state"),
                ["partial", "not_paid", "not_paid", "not_paid"],
            )
            self.assertEqual(
                all_subs.mapped("subscription_state"),
                ["3_progress", "6_churn", "6_churn", "6_churn"],
            )
            self.assertEqual(
                sub3.close_reason_id.id,
                self.env.ref("sale_subscription.close_reason_unpaid_subscription").id,
            )
            self.assertEqual(sub0.subscription_state, "3_progress")

        with freeze_time("2023-01-07"):
            self.env["sale.order"].sudo()._cron_subscription_expiration()
            self.assertEqual(sub0.subscription_state, "6_churn")

    def test_close_unpaid_contracts_bis(self):
        with freeze_time("2023-01-01"):
            sub = self.env["sale.order"].create(
                {
                    "name": "Paid",
                    "partner_id": self.partner.id,
                    "payment_term_id": self.env.ref(
                        "payment_term.account_payment_term_21days"
                    ).id,
                    "template_id": self.templ_5_days.id,
                }
            )
            sub._onchange_template_id()
            sub.action_confirm()

            self.env["sale.order"]._cron_recurring_create_invoice()
            invoice_to_skip = sub.invoice_ids
        with freeze_time("2024-01-01"):
            self.env["sale.order"]._cron_recurring_create_invoice()
            invoice_to_pay = sub.invoice_ids - invoice_to_skip
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=invoice_to_pay.ids
            ).create(
                {
                    "currency_id": sub.currency_id.id,
                    "amount": 300,
                }
            )._create_payments()
        with freeze_time("2025-01-02"):
            self.env["sale.order"].sudo()._cron_subscription_expiration()
            self.assertEqual(sub.subscription_state, "3_progress")
        with freeze_time("2025-01-07"):
            self.env["sale.order"].sudo()._cron_subscription_expiration()
            self.assertEqual(sub.subscription_state, "6_churn")
            self.assertEqual(
                sub.close_reason_id.id,
                self.env.ref(
                    "sale_subscription.close_reason_auto_close_limit_reached"
                ).id,
            )

    def test_partial_payment(self):
        subscription = self.subscription
        subscription.action_confirm()

        reference = "CONTRACT-%s-%s" % (
            subscription.id,
            datetime.datetime.now().strftime("%y%m%d_%H%M%S%f"),
        )
        tx = self.env["payment.transaction"].create(
            self._get_payment_values(
                subscription, [], subscription.amount_total / 2.0, reference
            )
        )
        tx._set_done()
        tx._post_process()

        self.assertEqual(tx.state, "done")
        self.assertFalse(tx.invoice_ids, "We should not have created an invoice")
        self.assertFalse(
            subscription.invoice_ids,
            "We should not have created an invoice on the subscription",
        )
        self.assertEqual(
            subscription.start_date,
            subscription.next_invoice_date,
            "The subscription next invoice date should not have been updated",
        )

    def test_refund_next_invoice_date(self):
        with freeze_time("2023-01-18"):
            subscription = self.env["sale.order"].create(
                {
                    "partner_id": self.partner.id,
                    "plan_id": self.plan_month.id,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": self.product.name,
                                "product_id": self.product.id,
                                "product_qty": 3.0,
                                "price_unit": 12,
                            },
                        )
                    ],
                }
            )
            subscription.action_confirm()
            subscription._create_recurring_invoice()
            self.assertEqual(
                subscription.next_invoice_date,
                datetime.date(2023, 2, 18),
                "The next invoice date is incremented",
            )
            subscription._compute_invoices()
            inv = subscription.invoice_ids

            test_payment_token = (
                self.env["payment.token"]
                .sudo()
                .create(
                    {
                        "payment_details": "Test",
                        "partner_id": subscription.partner_id.id,
                        "provider_id": self.dummy_provider.id,
                        "payment_method_id": self.payment_method_id,
                        "provider_ref": "test",
                    }
                )
            )
            payment_with_token = self.env["account.payment"].create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "amount": subscription.amount_total,
                    "date": subscription.date_order,
                    "currency_id": subscription.currency_id.id,
                    "partner_id": subscription.partner_id.id,
                    "payment_token_id": test_payment_token.id,
                }
            )
            transaction_ids = payment_with_token._create_payment_transaction()
            transaction_ids._set_done()
            with freeze_time("2023-02-18"):
                subscription._create_recurring_invoice()
                self.assertEqual(
                    subscription.next_invoice_date,
                    datetime.date(2023, 3, 18),
                    "The next invoice date is incremented",
                )
            refund_wizard = (
                self.env["wizard.account.move.reverse"]
                .with_context(active_model="account.move", active_ids=inv.ids)
                .create(
                    {
                        "reason": "Test refund tax repartition",
                        "journal_id": inv.journal_id.id,
                    }
                )
            )
            res = refund_wizard.refund_moves()
            refund_move = self.env["account.move"].browse(res["res_id"])
            self.assertEqual(
                inv.reversal_move_ids,
                refund_move,
                "The initial move should be reversed",
            )
            self.assertEqual(
                subscription.next_invoice_date,
                datetime.date(2023, 3, 18),
                "The next invoice date not incremented",
            )

    def test_subscription_invoice_after_payment(self):
        self.amount = self.subscription.amount_total
        tx = self._create_transaction(
            flow="redirect", sale_order_ids=[self.subscription.id], state="done"
        )
        with mute_logger("odoo.addons.sale.models.payment_transaction"):
            tx._post_process()
        self.assertEqual(self.subscription.state, "done")
        self.assertEqual(len(self.subscription.invoice_ids), 1)
        self.assertEqual(self.subscription.invoice_ids.state, "posted")

    def test_subscription_invoice_after_payment_sale_automatic_invoice(self):
        self.env["ir.config_parameter"].set_param("sale.automatic_invoice", "True")

        def _post_process(self):
            self.invoice_ids.filtered(lambda inv: inv.state == "draft").action_post()

        ap_reconcile_after_done_post = patch(
            "odoo.addons.account_payment_provider.models.payment_transaction.PaymentTransaction._post_process",
            side_effect=_post_process,
            autospec=_post_process,
        )
        self.startPatcher(ap_reconcile_after_done_post)

        _send_invoice_mock = self.startPatcher(
            patch.object(
                self.env.registry["mixin.account.move.send"],
                "_generate_and_send_invoices",
                autospec=True,
            )
        )

        self.amount = self.subscription.amount_total
        tx = self._create_transaction(
            flow="redirect",
            sale_order_ids=[self.subscription.id],
            state="done",
            subscription_action="assign_token",
        )
        with mute_logger("odoo.addons.sale.models.payment_transaction"):
            tx._post_process()
        self.assertEqual(self.subscription.state, "done")
        self.assertEqual(len(self.subscription.invoice_ids), 1)
        self.assertEqual(self.subscription.invoice_ids.state, "posted")

    def test_manually_captured_payment_providers_not_allowed(self):
        self.provider.capture_manually = True

        compatible_providers = (
            self.env["payment.provider"]
            .sudo()
            ._get_compatible_providers(
                self.company.id,
                self.partner.id,
                self.amount,
                sale_order_id=self.subscription.id,
            )
        )

        self.assertNotIn(self.provider, compatible_providers)

    def test_exceeding_maximum_amount_providers_not_allowed(self):
        self.provider.maximum_amount = 1
        self.assertGreater(
            self.amount,
            self.provider.maximum_amount,
            "The subscription amount should be greater than the maximum amount on the provider for this test.",
        )

        compatible_providers = (
            self.env["payment.provider"]
            .sudo()
            ._get_compatible_providers(
                self.company.id,
                self.partner.id,
                self.amount,
                sale_order_id=self.subscription.id,
            )
        )

        self.assertNotIn(
            self.provider,
            compatible_providers,
            "The provider should not be proposed to the user because its maximum amount is too low to pay this subscription.",
        )

    def test_cancel_draft_invoice_unsuccessful_transaction(self):
        with freeze_time("2024-01-23"):
            subscription = self.env["sale.order"].create(
                {
                    "partner_id": self.user_portal.partner_id.id,
                    "template_id": self.subscription_tmpl.id,
                    "start_date": datetime.date(2024, 1, 15),
                }
            )
            subscription._onchange_template_id()
            test_payment_token = (
                self.env["payment.token"]
                .sudo()
                .create(
                    {
                        "payment_details": "Test",
                        "partner_id": self.user_portal.partner_id.id,
                        "provider_id": self.dummy_provider.id,
                        "payment_method_id": self.payment_method_id,
                        "provider_ref": "test",
                    }
                )
            )
            payment_with_token = self.env["account.payment"].create(
                {
                    "amount": subscription.amount_total,
                    "currency_id": subscription.currency_id.id,
                    "partner_id": self.user_portal.partner_id.id,
                    "payment_token_id": test_payment_token.id,
                }
            )
            transaction_ids = payment_with_token._create_payment_transaction()
            subscription.write({"transaction_ids": [Command.set(transaction_ids.ids)]})
            subscription.action_confirm()
            subscription._create_invoices(final=True)
            draft_invoice = subscription.line_ids.invoice_line_ids.move_id.filtered(
                lambda am: am.state == "draft"
            )
            transaction_ids._set_error("Payment declined!")
            transaction_ids._post_process()
            self.assertEqual(
                len(draft_invoice),
                1,
                "A single draft invoice must be created after the payment was done.",
            )
            self.assertFalse(
                subscription.pending_transaction,
                "Subscription doesn't have pending transaction after unsuccessful payment.",
            )
            self.assertFalse(
                subscription.payment_token_id,
                "The payment token should not be saved after the unsuccessful payment.",
            )
            self.assertEqual(
                draft_invoice.state,
                "cancel",
                "Draft invoice must be canceled after unsuccessful payment.",
            )

    def test_prevent_multiple_in_progress(self):
        with freeze_time("2024-01-01"):
            subscription = self.env["sale.order"].create(
                {
                    "partner_id": self.user_portal.partner_id.id,
                    "template_id": self.subscription_tmpl.id,
                    "start_date": datetime.date(2024, 1, 15),
                }
            )
            subscription._onchange_template_id()
            test_payment_token = (
                self.env["payment.token"]
                .sudo()
                .create(
                    {
                        "payment_details": "Test",
                        "partner_id": self.user_portal.partner_id.id,
                        "provider_id": self.dummy_provider.id,
                        "payment_method_id": self.payment_method_id,
                        "provider_ref": "test",
                    }
                )
            )
            subscription.action_confirm()
            inv = subscription._create_invoices(final=True)
            inv._post()
            action = subscription.prepare_renewal_order()
            renewal_so = self.env["sale.order"].browse(action["res_id"])
            renewal_so.action_confirm()
            payment_with_token = self.env["account.payment"].create(
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "amount": subscription.amount_total,
                    "date": subscription.date_order,
                    "currency_id": subscription.currency_id.id,
                    "partner_id": subscription.partner_id.id,
                    "payment_token_id": test_payment_token.id,
                }
            )
            transaction_ids = payment_with_token._create_payment_transaction()
            transaction_ids.sale_order_ids = [Command.set(renewal_so.ids)]
            transaction_ids.subscription_action = "automatic_send_mail"
            inv = renewal_so._create_invoices(final=True)
            inv._post()
            action = renewal_so.prepare_renewal_order()
            renewal_so2 = self.env["sale.order"].browse(action["res_id"])
            renewal_so2.action_confirm()
            transaction_ids._set_done()
            transaction_ids._post_process()
            self.assertEqual(subscription.subscription_state, "5_renewed")
            self.assertEqual(renewal_so.subscription_state, "5_renewed")
            self.assertEqual(renewal_so2.subscription_state, "3_progress")

    def test_negative_payment_handling(self):
        with freeze_time("2024-01-23"):
            test_payment_token = (
                self.env["payment.token"]
                .sudo()
                .create(
                    {
                        "payment_details": "Test",
                        "partner_id": self.user_portal.partner_id.id,
                        "provider_id": self.dummy_provider.id,
                        "payment_method_id": self.payment_method_id,
                        "provider_ref": "test",
                    }
                )
            )
            self.subscription.write(
                {
                    "start_date": False,
                    "next_invoice_date": False,
                    "payment_token_id": test_payment_token.id,
                    "client_order_ref": "Customer REF XXXXXXX",
                }
            )
            self.product5.product_tmpl_id.recurring_invoice = False
            non_recurring = self.env["sale.order.line"].create(
                {
                    "order_id": self.subscription.id,
                    "product_id": self.product5.id,
                    "price_unit": 1000,
                }
            )
            self.subscription.action_confirm()
            with patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=self._mock_subscription_do_payment,
            ):
                invoice = self.env["sale.order"]._create_recurring_invoice()
                txs_to_post_process = self.env["payment.transaction"].search(
                    [
                        ("state", "=", "done"),
                        ("is_post_processed", "=", False),
                        (
                            "last_state_change",
                            ">=",
                            datetime.datetime.now() - relativedelta(days=4),
                        ),
                    ]
                )
                txs_to_post_process._post_process()
            self.assertAlmostEqual(invoice.amount_total, 1123.1)
            self.assertAlmostEqual(invoice.amount_total_signed, 1123.1)
            self.assertEqual(invoice.move_type, "out_invoice", "This is an invoice")
            self.assertEqual(
                self.subscription.next_invoice_date, datetime.date(2024, 2, 23)
            )
        with freeze_time("2024-02-23"):
            non_recurring.product_qty = 0
            with patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=self._mock_subscription_do_payment,
            ):
                invoice2 = self.env["sale.order"]._create_recurring_invoice()
                txs_to_post_process = self.env["payment.transaction"].search(
                    [
                        ("state", "=", "done"),
                        ("is_post_processed", "=", False),
                        (
                            "last_state_change",
                            ">=",
                            datetime.datetime.now() - relativedelta(days=4),
                        ),
                    ]
                )
                txs_to_post_process._post_process()
            self.assertEqual(invoice2.move_type, "out_refund", "This is a refund")
            self.assertEqual(
                invoice2.state, "draft", "The invoice should not be posted"
            )
            self.assertAlmostEqual(invoice2.amount_total_signed, -1076.9)
            self.assertTrue(self.subscription.payment_exception)
            self.assertEqual(
                self.subscription.next_invoice_date,
                datetime.date(2024, 2, 23),
                "The next invoice date should not be updated",
            )

    def test_automate_payments_invoice_multiple_subscriptions(self):
        sub_params = {
            "partner_id": self.partner.id,
            "company_id": self.company.id,
            "template_id": self.subscription_tmpl.id,
        }
        subscription_1 = self.subscription.create(sub_params)
        subscription_2 = self.subscription.create(sub_params)
        for sub in [subscription_1, subscription_2]:
            sub._onchange_template_id()
            sub.action_confirm()

        invoice = (
            self.env["wizard.sale.order.invoice"]
            .create(
                {
                    "advance_payment_method": "delivered",
                    "sale_order_ids": [
                        Command.set((subscription_1 + subscription_2).ids)
                    ],
                    "consolidated_billing": True,
                }
            )
            ._create_invoices(subscription_1 + subscription_2)
        )

        for sub in [subscription_1, subscription_2]:
            self.assertTrue(sub in invoice.invoice_line_ids.subscription_id)

        test_payment_token = (
            self.env["payment.token"]
            .sudo()
            .create(
                {
                    "payment_details": "Test",
                    "partner_id": subscription_1.partner_id.id,
                    "provider_id": self.dummy_provider.id,
                    "payment_method_id": self.payment_method_id,
                    "provider_ref": "test",
                }
            )
        )

        subscriptions_sudo = invoice.sudo().invoice_line_ids.subscription_id
        tx_sudo = self._create_transaction(
            sale_order_ids=[Command.set(subscriptions_sudo.ids)],
            invoice_ids=[Command.set(invoice.ids)],
            subscription_action="assign_token",
            currency_id=invoice.sudo().currency_id.id,
            partner_id=self.partner.sudo().id,
            provider_id=self.dummy_provider.id,
            payment_method_id=self.payment_method_id,
            token_id=test_payment_token.id,
            amount=invoice.amount_total,
            flow="direct",
            landing_route="/my/invoices/%s?access_token=%s"
            % (invoice.id, invoice.access_token),
        )
        tx_sudo._set_done()
        tx_sudo._post_process()

        for sub in [subscription_1, subscription_2]:
            self.assertEqual(
                sub.payment_token_id.id,
                test_payment_token.id,
                "Token must be assigned to subscription after transaction creation.",
            )

    def test_successful_reopen_churned_subscription(self):
        with freeze_time("2025-08-08"):
            subscription = self.subscription
            subscription.action_confirm()
            subscription._create_recurring_invoice()

        with freeze_time("2025-09-14"):
            subscription.set_close(
                close_reason_id=self.env.ref(
                    "sale_subscription.close_reason_auto_close_limit_reached"
                ).id
            )

            self.assertEqual(
                subscription.subscription_state,
                "6_churn",
                "The subscription must be churned after closing it.",
            )

            cutoff_date = datetime.datetime.now().date() - relativedelta(
                days=subscription.plan_id.auto_close_limit
            )
            self.assertTrue(
                cutoff_date <= subscription.next_invoice_date,
                "For sub reopening, we must have payment date <= next invoice date.",
            )

            tx = self.env["payment.transaction"].create(
                self._get_payment_values(subscription, subscription.invoice_ids.ids)
            )
            tx._set_done()
            tx._post_process()
            self.assertEqual(tx.state, "done")
            self.assertEqual(
                subscription.subscription_state,
                "3_progress",
                "Churned subscription must be re-opened after paying the invoice.",
            )

    def test_successful_reopen_churned_subscription_manual(self):
        with freeze_time("2025-08-08"):
            subscription = self.subscription
            subscription.action_confirm()
            invoice = subscription._create_recurring_invoice()

        with freeze_time("2025-09-14"):
            subscription.set_close(
                close_reason_id=self.env.ref(
                    "sale_subscription.close_reason_auto_close_limit_reached"
                ).id
            )

            self.assertEqual(
                subscription.subscription_state,
                "6_churn",
                "The subscription must be churned after closing it.",
            )
            cutoff_date = datetime.datetime.now().date() - relativedelta(
                days=subscription.plan_id.auto_close_limit
            )
            self.assertTrue(
                cutoff_date <= subscription.next_invoice_date,
                "For sub reopening, we must have payment date cutoff_date <= next invoice date.",
            )

            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=invoice.ids
            ).create({})._create_payments()

            self.assertTrue(
                invoice.payment_state in ["in_payment", "paid"],
                "Ensure that the invoice's payment state is either 'in_payment' or 'paid'",
            )
            self.assertEqual(
                subscription.subscription_state,
                "3_progress",
                "Churned subscription must be re-opened after paying the invoice.",
            )

    def test_a_subscription_closed_on_purpose_stays_closed_when_paid(self):
        with freeze_time("2025-08-08"):
            subscription = self.subscription
            subscription.action_confirm()
            invoice = subscription._create_recurring_invoice()

        with freeze_time("2025-09-14"):
            subscription.set_close(
                close_reason_id=self.env.ref("sale_subscription.close_reason_1").id
            )
            tx = self.env["payment.transaction"].create(
                self._get_payment_values(subscription, invoice.ids)
            )
            tx._set_done()
            tx._post_process()

            self.assertEqual(tx.state, "done")
            self.assertEqual(subscription.subscription_state, "6_churn")

    def test_a_subscription_closed_on_purpose_stays_closed_when_paid_manually(self):
        with freeze_time("2025-08-08"):
            subscription = self.subscription
            subscription.action_confirm()
            invoice = subscription._create_recurring_invoice()

        with freeze_time("2025-09-14"):
            subscription.set_close(
                close_reason_id=self.env.ref("sale_subscription.close_reason_1").id
            )
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=invoice.ids
            ).create({})._create_payments()

            self.assertIn(invoice.payment_state, ["in_payment", "paid"])
            self.assertEqual(subscription.subscription_state, "6_churn")

    def test_a_paid_credit_note_does_not_reopen_a_churned_subscription(self):
        with freeze_time("2025-08-08"):
            subscription = self.subscription
            subscription.action_confirm()
            invoice = subscription._create_recurring_invoice()
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=invoice.ids
            ).create({"payment_date": invoice.date})._create_payments()
            subscription.set_close(
                close_reason_id=self.env.ref(
                    "sale_subscription.close_reason_auto_close_limit_reached"
                ).id
            )
            self.assertEqual(subscription.subscription_state, "6_churn")

            reversal = (
                self.env["wizard.account.move.reverse"]
                .with_context(active_model="account.move", active_ids=invoice.ids)
                .create({"reason": "Credit note", "journal_id": invoice.journal_id.id})
            )
            credit_note = self.env["account.move"].browse(
                reversal.refund_moves()["res_id"]
            )
            self.assertEqual(credit_note.move_type, "out_refund")
            credit_note.action_post()
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=credit_note.ids
            ).create({"payment_date": credit_note.date})._create_payments()

            self.assertIn(credit_note.payment_state, ["in_payment", "paid"])
            self.assertEqual(subscription.subscription_state, "6_churn")

    def test_unsuccessful_reopen_churned_subscription(self):
        subscription = self.subscription
        subscription.plan_id.auto_close_limit = 5
        subscription.action_confirm()
        subscription._create_recurring_invoice()
        subscription.set_close()

        late_payment_date = subscription.next_invoice_date + relativedelta(
            days=subscription.plan_id.auto_close_limit + 7
        )
        with freeze_time(late_payment_date):
            tx_2 = self.env["payment.transaction"].create(
                self._get_payment_values(subscription, subscription.invoice_ids.ids)
            )
            tx_2._set_done()
            tx_2._post_process()
            self.assertEqual(tx_2.state, "done")
            self.assertEqual(
                subscription.subscription_state,
                "6_churn",
                "Churned subscription must not re-open after the invoice late payment.",
            )

    def test_payment_pending(self):
        test_payment_token = (
            self.env["payment.token"]
            .sudo()
            .create(
                {
                    "payment_details": "Test",
                    "partner_id": self.user_portal.partner_id.id,
                    "provider_id": self.dummy_provider.id,
                    "payment_method_id": self.payment_method_id,
                    "provider_ref": "test",
                }
            )
        )
        self.subscription.write(
            {
                "payment_token_id": test_payment_token.id,
                "client_order_ref": "Customer REF XXXXXXX",
            }
        )
        self.subscription.action_confirm()
        with (
            patch(
                "odoo.addons.sale_subscription.models.sale_order.SaleOrder._do_payment",
                wraps=self._mock_subscription_do_payment_pending,
            ),
            self.mock_mail_gateway(),
        ):
            self.subscription._create_recurring_invoice()

        invoice = self.subscription.line_ids.invoice_line_ids.move_id
        self.assertTrue(
            self.subscription.pending_transaction,
            "The pending transaction flag should remain",
        )
        self.assertEqual(invoice.state, "draft", "The draft invoice should exist")
        self.assertEqual(
            self.subscription.next_invoice_date,
            self.subscription.start_date,
            "We should not have updated the next invoice date, as the invoice was unlinked",
        )
        invoice._post()
        self.assertFalse(
            self.subscription.pending_transaction,
            "The pending transaction flag should not remain",
        )

    def test_manual_invoice_from_other_company_website(self):
        company = self.env["res.company"].create({"name": "Website Company"})
        public_user = self.env.ref("base.public_user")
        public_user.sudo().write(
            {"company_id": company.id, "company_ids": [Command.set([company.id])]}
        )

        with freeze_time("2024-01-01"):
            subscription = self.subscription
            subscription.action_confirm()
            test_payment_token = (
                self.env["payment.token"]
                .sudo()
                .create(
                    {
                        "payment_details": "Test",
                        "partner_id": subscription.partner_id.id,
                        "provider_id": self.dummy_provider.id,
                        "payment_method_id": self.payment_method_id,
                        "provider_ref": "test",
                    }
                )
            )
            payment_with_token = self.env["account.payment"].create(
                {
                    "amount": subscription.amount_total,
                    "currency_id": subscription.currency_id.id,
                    "partner_id": self.user_portal.partner_id.id,
                    "payment_token_id": test_payment_token.id,
                }
            )
            inv = subscription._create_invoices()
            payment_with_token.move_id = inv.id
            payment_with_token.write({"state": "paid"})
            tx = payment_with_token._create_payment_transaction()
            subscription.write({"transaction_ids": [Command.set(tx.ids)]})
            tx._set_done()
            tx.with_user(public_user).sudo()._post_process()

    def test_subscription_invoice_after_second_period_payment(self):
        sub = self.subscription
        self.product5.recurring_invoice = False
        sub.line_ids = [
            Command.create(
                {
                    "name": "non recurring product",
                    "product_id": self.product5.id,
                    "product_qty": 1,
                }
            )
        ]
        sub.action_confirm()
        sub._create_invoices().action_post()
        invoice_1 = sub.invoice_ids
        self.assertNotEqual(
            sub.amount_total, invoice_1.amount_paid, "Subscription should not be paid"
        )

        self.assertEqual(sub.state, "done")
        self.assertEqual(len(sub.invoice_ids), 1)
        self.assertEqual(sub.invoice_ids.state, "posted")

        self.reference = "SECOND PERIOD"
        self.amount = sub._next_billing_details()["next_invoice_amount"]
        tx = self._create_transaction(
            flow="redirect", sale_order_ids=[sub.id], state="done"
        )
        with mute_logger("odoo.addons.sale.models.payment_transaction"):
            tx._post_process()
        invoice_2 = sub.invoice_ids - invoice_1
        self.assertEqual(
            self.amount, invoice_2.amount_paid, "Subscription should not be paid"
        )

        self.assertEqual(sub.state, "done")
        self.assertEqual(len(sub.invoice_ids), 2)
        self.assertEqual(sub.invoice_ids[1].state, "posted")

    def test_payment_link_wizard(self):
        with freeze_time("2025-04-15"):
            test_payment_token = (
                self.env["payment.token"]
                .sudo()
                .create(
                    {
                        "payment_details": "Test",
                        "partner_id": self.user_portal.partner_id.id,
                        "provider_id": self.dummy_provider.id,
                        "payment_method_id": self.payment_method_id,
                        "provider_ref": "test",
                    }
                )
            )
            self.subscription.write(
                {
                    "start_date": False,
                    "next_invoice_date": False,
                    "prepayment_percent": 50,
                    "payment_token_id": test_payment_token.id,
                    "client_order_ref": "Customer REF XXXXXXX",
                }
            )
            self.subscription.action_confirm()
            payment_vals = self.subscription._prepare_payment_link_vals()
            self.assertAlmostEqual(
                payment_vals["amount"],
                23.1,
                msg="Non invoiced SO have same behavior as recular SO",
            )
            self.assertAlmostEqual(
                payment_vals["amount_max"],
                23.1,
                msg="Non invoiced SO have same behavior as recular SO",
            )
        with freeze_time("2025-05-15"):
            inv = self.subscription._create_recurring_invoice()
            tx = self.env["payment.transaction"].create(
                self._get_payment_values(self.subscription, inv.ids)
            )
            tx._set_done()
            tx._post_process()
            payment_vals = self.subscription._prepare_payment_link_vals()
            self.assertAlmostEqual(
                payment_vals["amount"],
                23.1,
                msg="invoiced recurring SO have different behavior",
            )
            self.assertAlmostEqual(
                payment_vals["amount_max"],
                23.1,
                msg="invoiced recurring SO have different behavior",
            )

        with freeze_time("2025-06-15"):
            inv = self.subscription._create_recurring_invoice()
            tx = self.env["payment.transaction"].create(
                self._get_payment_values(
                    self.subscription, inv.ids, reference="PAYMENT2"
                )
            )
            tx._set_done()
            tx._post_process()
            payment_vals = self.subscription._prepare_payment_link_vals()
            self.assertAlmostEqual(
                payment_vals["amount"],
                23.1,
                msg="invoiced recurring SO have different behavior",
            )
            self.assertAlmostEqual(
                payment_vals["amount_max"],
                23.1,
                msg="invoiced recurring SO have different behavior",
            )
