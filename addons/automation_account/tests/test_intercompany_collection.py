from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests.common import new_test_user, tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestIntercompanyCollection(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.receiving = cls.company
        cls.owed = cls.env["res.company"].create(
            {
                "name": "TAA Owed Company",
                "currency_id": cls.receiving.currency_id.id,
            },
        )
        cls.env.user.company_ids |= cls.owed

        Account = cls.env["account.account"]
        cls.owed_receivable = Account.create(
            {
                "name": "TAA Owed Receivable",
                "code": "TAAIC110",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.link(cls.owed.id)],
            },
        )
        cls.owed_income = Account.create(
            {
                "name": "TAA Owed Income",
                "code": "TAAIC400",
                "account_type": "income",
                "company_ids": [Command.link(cls.owed.id)],
            },
        )
        cls.owed_by_receiving = Account.create(
            {
                "name": "TAA Owed By Receiving",
                "code": "TAAIC120",
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.link(cls.owed.id)],
            },
        )
        cls.receiving_owes = Account.create(
            {
                "name": "TAA Receiving Owes",
                "code": "TAAIC210",
                "account_type": "liability_payable",
                "reconcile": True,
                "company_ids": [Command.link(cls.receiving.id)],
            },
        )

        Journal = cls.env["account.journal"]
        cls.owed_sale_journal = Journal.create(
            {
                "name": "TAA Owed Sales",
                "code": "TAAIS",
                "type": "sale",
                "company_id": cls.owed.id,
            },
        )
        cls.owed_misc_journal = Journal.create(
            {
                "name": "TAA Owed Intercompany",
                "code": "TAAIM",
                "type": "general",
                "company_id": cls.owed.id,
            },
        )
        cls.owed.automation_intercompany_journal_id = cls.owed_misc_journal

        cls.partner.with_company(
            cls.owed
        ).property_account_receivable_id = cls.owed_receivable
        cls.receiving.partner_id.with_company(
            cls.owed
        ).property_account_receivable_id = cls.owed_by_receiving
        cls.owed.partner_id.with_company(
            cls.receiving
        ).property_account_payable_id = cls.receiving_owes

        cls.invoice = (
            cls.env["account.move"]
            .with_company(cls.owed)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": cls.partner.id,
                    "journal_id": cls.owed_sale_journal.id,
                    "invoice_date": "2026-08-20",
                    "company_id": cls.owed.id,
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "Owed item",
                                "quantity": 1,
                                "price_unit": 100.0,
                                "account_id": cls.owed_income.id,
                                "tax_ids": [],
                            },
                        ),
                    ],
                },
            )
        )
        cls.invoice.action_post()

    def setUp(self):
        super().setUp()
        self.step = self._make_step("pass")
        self.st_line = self._make_statement_line(100.0)
        self.runtime = self._make_runtime(
            company_ids=[Command.set((self.receiving | self.owed).ids)],
            st_line_id=self.st_line.id,
        )
        self.line = self.runtime.line_ids

    def _make_statement_line(self, amount):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "date": "2026-08-21",
                "payment_ref": "TAA intercompany collection",
                "partner_id": self.partner.id,
                "amount": amount,
            },
        )

    def _receivable_lines(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable",
        )

    def test_a_collection_banked_by_another_company_settles_both_ledgers(self):
        self.step.reconcile_statement_with_move(self.line, self.st_line, self.invoice)

        self.assertTrue(self.st_line.is_reconciled)
        owed_line = self.st_line.move_id.line_ids.filtered(
            lambda line: line.account_id == self.receiving_owes,
        )
        self.assertEqual(owed_line.partner_id, self.owed.partner_id)
        self.assertAlmostEqual(owed_line.balance, -100.0)

        bridge = self.line.created_record_ref
        self.assertEqual(bridge.company_id, self.owed)
        self.assertEqual(bridge.journal_id, self.owed_misc_journal)
        self.assertEqual(bridge.state, "posted")
        mirror = bridge.line_ids.filtered(
            lambda line: line.account_id == self.owed_by_receiving,
        )
        self.assertEqual(mirror.partner_id, self.receiving.partner_id)
        self.assertAlmostEqual(mirror.balance, 100.0)

        self.assertTrue(self._receivable_lines(self.invoice).reconciled)
        self.assertIn(self.invoice.payment_state, ("paid", "in_payment"))

    def test_a_mirror_on_the_customer_account_keeps_the_intercompany_balance(self):
        self.receiving.partner_id.with_company(
            self.owed
        ).property_account_receivable_id = self.owed_receivable

        self.step.reconcile_statement_with_move(self.line, self.st_line, self.invoice)

        mirror = self.line.created_record_ref.line_ids.filtered(
            lambda line: line.partner_id == self.receiving.partner_id,
        )
        self.assertEqual(mirror.account_id, self.owed_receivable)
        self.assertFalse(mirror.reconciled)
        self.assertAlmostEqual(mirror.amount_residual, 100.0)
        self.assertIn(self.invoice.payment_state, ("paid", "in_payment"))

    def test_a_partial_collection_leaves_the_rest_of_the_invoice_open(self):
        st_line = self._make_statement_line(40.0)

        self.step.reconcile_statement_with_move(self.line, st_line, self.invoice)

        self.assertTrue(st_line.is_reconciled)
        self.assertAlmostEqual(self.invoice.amount_residual, 60.0)

    def test_without_a_journal_the_step_stops_before_touching_the_bank_line(self):
        self.owed.automation_intercompany_journal_id = False

        with self.assertRaises(UserError):
            self.step.reconcile_statement_with_move(
                self.line,
                self.st_line,
                self.invoice,
            )

        self.assertFalse(self.st_line.is_reconciled)
        self.assertFalse(self._receivable_lines(self.invoice).reconciled)

    def test_without_the_mirror_receivable_account_the_step_stops(self):
        self.receiving.partner_id.with_company(
            self.owed
        ).property_account_receivable_id = False

        with self.assertRaises(UserError):
            self.step.reconcile_statement_with_move(
                self.line,
                self.st_line,
                self.invoice,
            )

        self.assertFalse(self.st_line.is_reconciled)

    def test_money_going_out_is_not_settled_for_another_company(self):
        st_line = self._make_statement_line(-100.0)

        with self.assertRaises(UserError):
            self.step.reconcile_statement_with_move(self.line, st_line, self.invoice)

        self.assertFalse(st_line.is_reconciled)

    def test_a_step_of_an_intercompany_run_sees_both_companies(self):
        step = self._make_step(
            "if env.company != record.runtime_id.company_ids[:1]"
            " or record.runtime_id.company_ids - env.companies:\n"
            "    raise UserError('the step cannot see both companies')\n"
            "action.mark_action_done_and_continue(record)",
            name="Scope",
        )
        runtime = self._make_runtime(
            company_ids=[Command.set((self.receiving | self.owed).ids)],
        )
        line = runtime.line_ids.filtered(lambda l: l.action_id == step)

        line.with_context(allowed_company_ids=[self.receiving.id]).action_execute()

        self.assertEqual(line.state, "done")

    def test_a_single_company_run_keeps_the_switcher_companies(self):
        step = self._make_step(
            "if env.companies != env['res.company'].browse(%d):\n"
            "    raise UserError('the company scope changed')\n"
            "action.mark_action_done_and_continue(record)" % self.receiving.id,
            name="Scope",
        )
        runtime = self._make_runtime()
        line = runtime.line_ids.filtered(lambda l: l.action_id == step)

        line.with_context(allowed_company_ids=[self.receiving.id]).action_execute()

        self.assertEqual(line.state, "done")

    def test_a_user_without_the_ending_company_is_told_which_one(self):
        user = new_test_user(
            self.env,
            login="taa_one_company",
            groups="base.group_user",
            company_id=self.receiving.id,
            company_ids=[Command.set(self.receiving.ids)],
        )

        with self.assertRaisesRegex(UserError, self.runtime.name):
            self.runtime.with_user(user)._execution_company_ids()
