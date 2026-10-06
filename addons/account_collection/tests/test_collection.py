from datetime import date, timedelta

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestCollection(CollectionCommon):
    def test_a_collection_settles_the_invoice_on_the_day_the_customer_paid(self):
        invoice = self._post_invoice(1000.0)
        paid_on = self.today - timedelta(days=2)

        payment = self._collect(invoice, 1000.0, date=paid_on)

        self.assertEqual(payment.date, paid_on)
        self.assertEqual(payment.collector_id, self.collector)
        self.assertEqual(payment.collection_method, "cash")
        self.assertEqual(
            payment.state,
            "in_process" if self.env["account.move"]._has_full_accounting() else "paid",
        )
        self.assertTrue(payment.is_in_custody)
        self.assertFalse(payment.is_bank_matched)
        self.assertTrue(payment.is_invoice_reconciled)
        self.assertEqual(invoice.amount_residual, 0.0)
        custody_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.custody_account
        )
        self.assertEqual(custody_line.debit, 1000.0)
        self.assertFalse(custody_line.reconciled)

    def test_the_custody_item_is_the_collectors_and_the_settlement_the_customers(
        self,
    ):
        invoice = self._post_invoice(1000.0)

        payment = self._collect(invoice, 1000.0)

        custody_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id == self.custody_account
        )
        receivable_line = payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        self.assertEqual(custody_line.partner_id, self.collector.partner_id)
        self.assertEqual(receivable_line.partner_id, invoice.commercial_partner_id)
        self.assertEqual(payment.partner_id, invoice.commercial_partner_id)

    def test_custody_is_due_after_working_days(self):
        config = self.company_data["company"].account_config_id
        config.collection_custody_days_cash = 1
        config.collection_custody_days_check = 2
        friday = date(2026, 10, 2)

        cash = self._collect(self._post_invoice(100.0), 100.0, date=friday)
        check = self._collect(
            self._post_invoice(100.0), 100.0, date=friday, method="check"
        )

        self.assertEqual(cash.date_custody_due, date(2026, 10, 5))
        self.assertEqual(check.date_custody_due, date(2026, 10, 6))

    def test_overdue_custody_reaches_the_supervisor_a_working_day_later(self):
        config = self.company_data["company"].account_config_id
        config.collection_custody_days_cash = 1
        config.collection_supervisor_id = self.treasurer
        just_late = self._collect(
            self._post_invoice(100.0),
            100.0,
            date=self.today - timedelta(days=2),
        )
        long_late = self._collect(
            self._post_invoice(100.0),
            100.0,
            date=self.today - timedelta(days=10),
        )
        just_late.date_custody_due = self.today - timedelta(days=1)

        self.env["account.payment"]._cron_notify_overdue_custody()

        self.assertIn(self.collector, just_late.activity_ids.user_id)
        self.assertNotIn(self.treasurer, just_late.activity_ids.user_id)
        self.assertIn(self.collector, long_late.activity_ids.user_id)
        self.assertIn(self.treasurer, long_late.activity_ids.user_id)

    def test_the_custody_status_reads_the_limit_and_the_overdue(self):
        config = self.company_data["company"].account_config_id
        config.collection_custody_days_cash = 1
        config.collection_custody_limit = 500.0
        company = self.company_data["company"]
        self._collect(self._post_invoice(300.0), 300.0)
        status = self.collector.with_user(self.collector)._get_custody_status(company)
        self.assertEqual(status["amount"], 300.0)
        self.assertFalse(status["over_limit"])
        self.assertFalse(status["overdue_count"])

        self._collect(
            self._post_invoice(300.0), 300.0, date=self.today - timedelta(days=10)
        )
        status = self.collector._get_custody_status(company)
        self.assertTrue(status["over_limit"])
        self.assertEqual(status["overdue_count"], 1)
        self.assertEqual(status["overdue_amount"], 300.0)

    def test_a_partial_collection_leaves_the_rest_open(self):
        invoice = self._post_invoice(1000.0)

        payment = self._collect(invoice, 400.0)

        self.assertEqual(payment.amount, 400.0)
        self.assertEqual(invoice.amount_residual, 600.0)
        self.assertEqual(invoice.payment_state, "partial")

    def test_a_collector_without_the_privilege_cannot_record_a_payment(self):
        invoice = self._post_invoice(1000.0)
        with self.assertRaises(AccessError):
            invoice.with_user(self.collector)._create_collection_payment(
                1000.0, self.today, "cash", self.collector, self.custody_journal
            )

    def test_a_collector_reads_only_their_own_collections(self):
        mine = self._collect(self._post_invoice(100.0), 100.0)
        theirs = self._collect(
            self._post_invoice(200.0), 200.0, collector=self.other_collector
        )
        visible = (
            self.env["account.payment"]
            .with_user(self.collector)
            .search([("id", "in", (mine | theirs).ids)])
        )
        self.assertEqual(visible, mine)

    def test_a_custody_payment_names_its_collector(self):
        with self.assertRaises(ValidationError):
            self.env["account.payment"].create(
                {
                    "amount": 10.0,
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner_a.id,
                    "journal_id": self.custody_journal.id,
                }
            )

    def test_a_custody_journal_books_to_an_outstanding_account(self):
        journal = self.env["account.journal"].create(
            {"name": "Bad custody", "code": "BADC", "type": "cash"}
        )
        with self.assertRaises(ValidationError):
            journal.is_collection_custody = True

    def test_only_customer_invoices_are_collected(self):
        bill = self.init_invoice("in_invoice", amounts=[100.0], taxes=[], post=True)
        with self.assertRaises(UserError):
            self._collect(bill, 100.0)

    def test_overdue_custody_reminds_the_collector_once(self):
        self.company_data["company"].account_config_id.collection_custody_days_cash = 1
        old = self._collect(
            self._post_invoice(100.0), 100.0, date=self.today - timedelta(days=5)
        )
        recent = self._collect(self._post_invoice(100.0), 100.0)

        self.env["account.payment"]._cron_notify_overdue_custody()
        self.env["account.payment"]._cron_notify_overdue_custody()

        self.assertEqual(len(old.activity_ids), 1)
        self.assertEqual(old.activity_ids.user_id, self.collector)
        self.assertFalse(recent.activity_ids)
