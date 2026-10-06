from datetime import timedelta

from odoo import Command
from odoo.exceptions import UserError
from odoo.fields import Date
from odoo.tests.common import TransactionCase, tagged

from .common import book_payment_entries


@tagged("post_install", "-at_install")
class TestCreditProvision(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.config = cls.env["credit.config"]._for(cls.company)
        Account = cls.env["account.account"]
        cls.expense = Account.create(
            {"name": "Bad debt", "code": "PROV6", "account_type": "expense"}
        )
        cls.allowance = Account.create(
            {
                "name": "Allowance for doubtful accounts",
                "code": "PROV1",
                "account_type": "asset_current",
                "reconcile": False,
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.sale_journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.company.id)], limit=1
        )
        cls.config.write(
            {
                "provision_journal_id": cls.journal.id,
                "provision_expense_account_id": cls.expense.id,
                "provision_allowance_account_id": cls.allowance.id,
            }
        )
        cls.matrix = cls.env.ref("account_credit.provision_matrix_default")
        cls.grade = cls.env["credit.grade"].create({"name": "Provision grade"})
        cls.product = cls.env["product.product"].create(
            {"name": "Provision product", "list_price": 100.0}
        )
        book_payment_entries(cls.env)
        cls.partner = cls.env["res.partner"].create(
            {"name": "Provisioned", "is_company": True, "credit_grade_id": cls.grade.id}
        )

    def _invoice(self, amount, due_days_ago):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.sale_journal.id,
                "invoice_date": Date.today() - timedelta(days=due_days_ago + 30),
                "invoice_date_due": Date.today() - timedelta(days=due_days_ago),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.with_context(credit_override=True).action_post()
        return invoice

    def _run(self, date=None):
        run = self.env["credit.provision.run"].create(
            {"company_id": self.company.id, "date": date or Date.today()}
        )
        run.action_compute()
        return run

    def test_the_matrix_rates_open_receivables_by_aging_bucket(self):
        self._invoice(1000.0, due_days_ago=-10)
        self._invoice(2000.0, due_days_ago=45)
        self._invoice(500.0, due_days_ago=200)
        run = self._run()
        by_bucket = {line.bucket: line for line in run.line_ids}
        self.assertEqual(by_bucket["current"].amount, 1000.0)
        self.assertEqual(by_bucket["current"].rate, 1.0)
        self.assertEqual(by_bucket["b31_60"].amount, 2000.0)
        self.assertEqual(by_bucket["b31_60"].expected_loss, 200.0)
        self.assertEqual(by_bucket["b180_plus"].expected_loss, 500.0)
        self.assertEqual(run.total_exposure, 3500.0)
        self.assertEqual(run.total_expected_loss, 10.0 + 200.0 + 500.0)
        self.assertEqual(run.state, "computed")

    def test_a_grade_specific_rate_wins_over_the_generic_one(self):
        self.matrix.line_ids = [
            Command.create(
                {"grade_id": self.grade.id, "bucket": "current", "rate": 5.0}
            )
        ]
        self._invoice(1000.0, due_days_ago=-10)
        run = self._run()
        self.assertEqual(run.line_ids.rate, 5.0)
        self.assertEqual(run.total_expected_loss, 50.0)

    def test_posting_books_the_change_against_the_previous_run(self):
        self._invoice(2000.0, due_days_ago=45)
        first = self._run(Date.today() - timedelta(days=1))
        first.action_post()
        self.assertEqual(first.state, "posted")
        move = first.move_id
        self.assertEqual(move.state, "posted")
        expense_line = move.line_ids.filtered(lambda l: l.account_id == self.expense)
        allowance_line = move.line_ids.filtered(
            lambda l: l.account_id == self.allowance
        )
        self.assertEqual(expense_line.debit, 200.0)
        self.assertEqual(allowance_line.credit, 200.0)

        self._invoice(1000.0, due_days_ago=200)
        second = self._run()
        self.assertEqual(second.previous_run_id, first)
        self.assertEqual(second.total_expected_loss, 200.0 + 1000.0)
        self.assertEqual(second.amount_to_book, 1000.0)
        second.action_post()
        booked = second.move_id.line_ids.filtered(
            lambda l: l.account_id == self.expense
        )
        self.assertEqual(booked.debit, 1000.0)

    def test_a_release_credits_the_expense(self):
        invoice = self._invoice(2000.0, due_days_ago=45)
        first = self._run(Date.today() - timedelta(days=1))
        first.action_post()
        self.env["wizard.account.move.line.pay"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"payment_date": Date.today()})._create_payments()
        second = self._run()
        self.assertEqual(second.total_expected_loss, 0.0)
        self.assertEqual(second.amount_to_book, -200.0)
        second.action_post()
        released = second.move_id.line_ids.filtered(
            lambda l: l.account_id == self.expense
        )
        self.assertEqual(released.credit, 200.0)

    def test_posting_needs_the_accounts(self):
        self.config.write({"provision_allowance_account_id": False})
        self._invoice(2000.0, due_days_ago=45)
        run = self._run()
        with self.assertRaises(UserError):
            run.action_post()

    def test_cancelling_a_posted_run_cancels_its_entry(self):
        self._invoice(2000.0, due_days_ago=45)
        run = self._run()
        run.action_post()
        run.action_cancel()
        self.assertEqual(run.state, "cancel")
        self.assertEqual(run.move_id.state, "cancel")
