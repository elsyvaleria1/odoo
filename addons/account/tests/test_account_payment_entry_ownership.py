from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPaymentLineRoles(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.receivable = cls.company_data["default_account_receivable"]

    def _payment(self, post=True, **vals):
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                **vals,
            }
        )
        if post:
            payment.action_post()
        return payment

    def _roles(self, payment):
        return sorted(
            (line.payment_role, line.account_id.id, line.balance)
            for line in payment.move_id.line_ids
        )

    def test_generated_lines_carry_their_role(self):
        payment = self._payment()

        self.assertEqual(
            self._roles(payment),
            [
                ("counterpart", self.receivable.id, -100.0),
                ("liquidity", payment.outstanding_account_id.id, 100.0),
            ],
        )
        liquidity, counterpart, other = payment._seek_for_lines()
        self.assertEqual(liquidity.payment_role, "liquidity")
        self.assertEqual(counterpart.payment_role, "counterpart")
        self.assertFalse(other)

    def test_write_off_on_a_receivable_account_stays_a_write_off(self):
        second_receivable = self.copy_account(self.receivable)
        payment = self.env["account.payment"].create(
            {
                "amount": 90.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "write_off_line_vals": [
                    {
                        "name": "discount",
                        "account_id": second_receivable.id,
                        "partner_id": self.partner_a.id,
                        "currency_id": self.company_data["currency"].id,
                        "amount_currency": 10.0,
                        "balance": 10.0,
                    }
                ],
            }
        )

        payment.date = "2026-08-02"

        self.assertEqual(
            sorted(
                (line.account_id.id, line.balance) for line in payment.move_id.line_ids
            ),
            sorted(
                [
                    (self.receivable.id, -100.0),
                    (payment.outstanding_account_id.id, 90.0),
                    (second_receivable.id, 10.0),
                ]
            ),
        )


@tagged("post_install", "-at_install")
class TestPaymentCounterpartAccount(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.payable_nf = cls.company_data["default_account_payable"]
        cls.payable_ff = cls.copy_account(cls.payable_nf, {"name": "Payable FF"})
        cls.partner_a.property_account_payable_id = cls.payable_nf
        cls.partner_b.property_account_payable_id = cls.payable_nf

    def _bill_on(self, account, amount=100.0):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-07-07",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "goods",
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        bill.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        ).account_id = account
        bill.action_post()
        return bill

    def _vendor_payment(self, **vals):
        return self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-07-07",
                "partner_id": self.partner_a.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "journal_id": self.bank_journal.id,
                **vals,
            }
        )

    def _ambiguous_candidates(self):
        accounts = self.payable_ff | self.payable_nf
        return patch.object(
            type(self.env["account.payment"]),
            "_get_counterpart_account_candidates",
            lambda payment: accounts,
        )

    def test_settled_account_survives_contact_and_date_edits(self):
        bill = self._bill_on(self.payable_ff)
        payment = self._register_payment(bill, payment_date="2026-07-17")
        self.assertEqual(payment.destination_account_id, self.payable_ff)
        self.assertEqual(
            bill.payment_state, self.env["account.move"]._get_invoice_in_payment_state()
        )
        contact = self.env["res.partner"].create(
            {"name": "Accounts payable desk", "parent_id": self.partner_a.id}
        )

        payment.action_draft()
        payment.partner_id = contact
        payment.date = "2026-07-25"
        payment.action_post()

        counterpart = payment._seek_for_lines()[1]
        self.assertEqual(payment.destination_account_id, self.payable_ff)
        self.assertEqual(counterpart.account_id, self.payable_ff)
        self.assertEqual(
            bill.payment_state, self.env["account.move"]._get_invoice_in_payment_state()
        )

    def test_a_settled_account_lapses_with_its_settled_documents(self):
        bill = self._bill_on(self.payable_ff)
        payment = self._register_payment(bill, payment_date="2026-07-17")
        payment.action_draft()
        payment.move_id.line_ids.remove_move_reconcile()
        bill.matched_payment_ids = [Command.unlink(payment.id)]

        payment.partner_id = self.partner_b

        self.assertRecordValues(
            payment,
            [
                {
                    "destination_account_id": self.payable_nf.id,
                    "counterpart_account_source": "default",
                }
            ],
        )

    def test_unambiguous_partner_property_is_the_default(self):
        payment = self._vendor_payment()

        self.assertEqual(payment.destination_account_id, self.payable_nf)
        self.assertEqual(payment.counterpart_account_source, "default")
        self.assertFalse(payment.is_counterpart_account_ambiguous)

    def test_ambiguous_advance_requires_an_explicit_choice(self):
        with self._ambiguous_candidates():
            payment = self._vendor_payment()
            self.assertFalse(payment.destination_account_id)
            self.assertTrue(payment.is_counterpart_account_ambiguous)
            with self.assertRaisesRegex(UserError, "Choose the counterpart account"):
                payment.action_post()

            payment.destination_account_id = self.payable_ff
            self.assertEqual(payment.counterpart_account_source, "explicit")
            payment.partner_id = self.partner_b
            payment.action_post()

        self.assertEqual(payment.destination_account_id, self.payable_ff)
        self.assertEqual(payment._seek_for_lines()[1].account_id, self.payable_ff)

    def test_explicit_choice_survives_a_partner_change(self):
        payment = self._vendor_payment(destination_account_id=self.payable_ff.id)
        self.assertEqual(payment.counterpart_account_source, "explicit")

        payment.partner_id = self.partner_b

        self.assertEqual(payment.destination_account_id, self.payable_ff)


@tagged("post_install", "-at_install")
class TestPaymentEntryOwnership(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.receivable = cls.company_data["default_account_receivable"]
        cls.other_receivable = cls.copy_account(cls.receivable, {"name": "AR NF"})
        cls.expense = cls.company_data["default_account_expense"]

    def _payment(self, **vals):
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                **vals,
            }
        )
        payment.action_post()
        return payment

    def _invoice(self, account=None):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "goods",
                            "price_unit": 100.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        if account:
            invoice.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            ).account_id = account
        invoice.action_post()
        return invoice

    def test_generated_lines_refuse_account_edits_on_the_entry(self):
        payment = self._payment()
        liquidity, counterpart, _other = payment._seek_for_lines()

        with self.assertRaisesRegex(UserError, "can only change through it"):
            counterpart.account_id = self.other_receivable
        with self.assertRaisesRegex(UserError, "can only change through it"):
            liquidity.partner_id = self.partner_b

        payment.action_draft()
        with self.assertRaisesRegex(UserError, "can only change through it"):
            payment.move_id.write(
                {
                    "line_ids": [
                        Command.update(counterpart.id, {"account_id": self.expense.id})
                    ]
                }
            )
        with self.assertRaisesRegex(UserError, "can only be removed"):
            liquidity.unlink()
        with self.assertRaisesRegex(UserError, "can only change through it"):
            payment.move_id.date = "2026-08-02"
        self.assertEqual(counterpart.account_id, self.receivable)

    def test_labels_and_write_off_accounts_stay_editable(self):
        payment = self.env["account.payment"].create(
            {
                "amount": 90.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "write_off_line_vals": [
                    {
                        "name": "discount",
                        "account_id": self.expense.id,
                        "partner_id": self.partner_a.id,
                        "currency_id": self.company_data["currency"].id,
                        "amount_currency": 10.0,
                        "balance": 10.0,
                    }
                ],
            }
        )
        liquidity, _counterpart, write_off = payment._seek_for_lines()
        other_expense = self.copy_account(self.expense)

        liquidity.name = "relabelled"
        write_off.account_id = other_expense
        payment.date = "2026-08-02"
        payment.action_post()

        self.assertEqual(write_off.account_id, other_expense)
        self.assertEqual(payment.state, "in_process")
        with self.assertRaisesRegex(UserError, "can only change through it"):
            write_off.balance = 20.0

    def test_posting_refuses_an_entry_that_no_longer_matches(self):
        payment = self._payment()
        payment.action_draft()
        counterpart = payment._seek_for_lines()[1]
        counterpart.with_context(
            entry_owner_sync=True
        ).account_id = self.other_receivable

        with self.assertRaisesRegex(UserError, "no longer matches"):
            payment.move_id.action_post()
        with self.assertRaisesRegex(UserError, "no longer matches"):
            payment.action_post()

    def test_correct_accounts_rebuilds_the_entry_through_the_payment(self):
        invoice = self._invoice()
        payment = self._register_payment(invoice, payment_date="2026-08-01")
        new_liquidity = self.copy_account(payment.outstanding_account_id)

        wizard = (
            self.env["wizard.account.payment.correct.accounts"]
            .with_context(default_payment_id=payment.id)
            .create({})
        )
        self.assertFalse(wizard.is_locked)
        wizard.liquidity_account_id = new_liquidity
        wizard.action_correct()

        self.assertEqual(payment.outstanding_account_id, new_liquidity)
        self.assertEqual(payment._seek_for_lines()[0].account_id, new_liquidity)
        self.assertEqual(payment.move_id.state, "posted")
        self.assertEqual(
            invoice.payment_state,
            self.env["account.move"]._get_invoice_in_payment_state(),
        )
        self.assertIn("Liquidity account", payment.message_ids[0].body)

        wizard = (
            self.env["wizard.account.payment.correct.accounts"]
            .with_context(default_payment_id=payment.id)
            .create({"counterpart_account_id": self.other_receivable.id})
        )
        wizard.action_correct()
        self.assertEqual(payment.destination_account_id, self.other_receivable)
        self.assertEqual(payment.counterpart_account_source, "explicit")
        self.assertEqual(payment._seek_for_lines()[1].account_id, self.other_receivable)

    def test_correct_accounts_in_a_locked_period_reclassifies(self):
        payment = self._payment(destination_account_id=self.other_receivable.id)
        self.env.company.account_config_id.fiscalyear_lock_date = "2026-08-31"
        entry_lines = payment.move_id.line_ids
        before = sorted(
            entry_lines.mapped(lambda line: (line.account_id.id, line.balance))
        )

        wizard = (
            self.env["wizard.account.payment.correct.accounts"]
            .with_context(default_payment_id=payment.id)
            .create({"date": "2026-09-05"})
        )
        self.assertTrue(wizard.is_locked)
        wizard.counterpart_account_id = self.receivable
        wizard.action_correct()

        reclass = self.env["account.move"].search(
            [("reclassified_payment_id", "=", payment.id)]
        )
        self.assertEqual(reclass.state, "posted")
        self.assertEqual(
            sorted(
                reclass.line_ids.mapped(lambda line: (line.account_id.id, line.balance))
            ),
            sorted([(self.other_receivable.id, 100.0), (self.receivable.id, -100.0)]),
        )
        self.assertEqual(
            sorted(
                payment.move_id.line_ids.mapped(
                    lambda line: (line.account_id.id, line.balance)
                )
            ),
            before,
        )
        self.assertTrue(payment._seek_for_lines()[1].reconciled)
        self.assertEqual(payment.destination_account_id, self.other_receivable)


@tagged("post_install", "-at_install")
class TestStatementLineEntryOwnership(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _st_line(self, amount=100.0):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "date": "2026-08-01",
                "payment_ref": "transfer 42",
                "partner_id": self.partner_a.id,
                "amount": amount,
            }
        )

    def _invoice(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "goods",
                            "price_unit": 100.0,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def test_the_transaction_owns_its_entry_one_way(self):
        st_line = self._st_line()
        liquidity, suspense, other = st_line._seek_for_lines()
        self.assertEqual(liquidity.payment_role, "liquidity")
        self.assertEqual(suspense.payment_role, "suspense")
        self.assertFalse(other)
        expense = self.company_data["default_account_expense"]

        with self.assertRaisesRegex(UserError, "can only change through it"):
            liquidity.account_id = expense
        with self.assertRaisesRegex(UserError, "can only change through it"):
            suspense.balance = -50.0
        with self.assertRaisesRegex(UserError, "can only change through it"):
            st_line.move_id.partner_id = self.partner_b

        liquidity.name = "relabelled on the entry"
        self.assertEqual(st_line.payment_ref, "transfer 42")

        st_line.write({"amount": 80.0, "partner_id": self.partner_b.id})
        self.assertEqual(
            sorted(
                (line.payment_role, line.balance, line.partner_id.id)
                for line in st_line.line_ids
            ),
            [
                ("liquidity", 80.0, self.partner_b.id),
                ("suspense", -80.0, self.partner_b.id),
            ],
        )
        self.assertEqual(st_line.move_id.partner_id, self.partner_b)

    def test_a_matched_transaction_is_corrected_by_undoing_its_matching(self):
        invoice = self._invoice()
        st_line = self._st_line()
        st_line.set_line_bank_statement_line(
            invoice.line_ids.filtered(
                lambda line: line.display_type == "payment_term"
            ).ids
        )
        self.assertTrue(st_line.is_reconciled)

        with self.assertRaisesRegex(UserError, "Undo the reconciliation first"):
            st_line.amount = 80.0

        st_line.action_undo_reconciliation()
        st_line.amount = 80.0

        liquidity, suspense, other = st_line._seek_for_lines()
        self.assertEqual((liquidity.balance, suspense.balance), (80.0, -80.0))
        self.assertFalse(other)
        self.assertEqual(invoice.payment_state, "not_paid")

    def test_assigning_an_account_to_the_open_balance_ends_its_suspense_role(self):
        st_line = self._st_line(amount=-30.0)
        suspense = st_line._seek_for_lines()[1]
        expense = self.company_data["default_account_expense"]

        st_line.set_account_bank_statement_line(suspense.ids, expense.id)

        self.assertEqual(suspense.account_id, expense)
        self.assertFalse(suspense.payment_role)
        self.assertTrue(st_line.is_reconciled)


@tagged("post_install", "-at_install")
class TestAdvanceApplication(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.payable = cls.company_data["default_account_payable"]
        cls.advances = cls.env["account.account"].create(
            {
                "name": "Supplier advances",
                "code": "ADV001",
                "account_type": "asset_prepayments",
                "reconcile": True,
            }
        )
        cls.third_party = cls.env["account.account"].create(
            {
                "name": "Paid by a third party",
                "code": "TPP001",
                "account_type": "liability_current",
                "reconcile": True,
            }
        )
        cls.misc_journal = cls.company_data["default_journal_misc"]

    def _bill(self, amount=100.0):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-08-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "goods",
                            "price_unit": amount,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _advance(self, amount):
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": "2026-07-15",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.advances.id,
                            "partner_id": self.partner_a.id,
                            "balance": amount,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_journal_bank"
                            ].default_account_id.id,
                            "balance": -amount,
                        }
                    ),
                ],
            }
        )
        entry.action_post()
        return entry.line_ids.filtered(lambda line: line.account_id == self.advances)

    def _wizard(self, bill, **vals):
        return (
            self.env["wizard.account.move.apply.advance"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create(vals)
        )

    def test_a_payment_that_moves_no_money_is_refused(self):
        advance_journal = self.company_data["default_journal_cash"].copy(
            {"name": "Supplier advances", "code": "ANT"}
        )
        advance_journal.default_account_id = self.advances
        for channel in advance_journal.outbound_payment_channel_ids:
            channel.payment_account_id = self.advances
        payment = self.env["account.payment"].create(
            {
                "amount": 100.0,
                "date": "2026-08-01",
                "partner_id": self.partner_a.id,
                "partner_type": "supplier",
                "payment_type": "outbound",
                "journal_id": advance_journal.id,
            }
        )

        with self.assertRaisesRegex(UserError, "use Apply Advance"):
            payment.action_post()

    def test_an_advance_pays_a_bill_without_a_payment(self):
        advance = self._advance(60.0)
        bill = self._bill(100.0)

        wizard = self._wizard(bill, advance_line_ids=[Command.set(advance.ids)])
        self.assertIn(advance, wizard.available_advance_line_ids)
        self.assertEqual(wizard.amount, 60.0)
        wizard.action_apply()

        entry = advance.matched_credit_ids.credit_move_id.move_id
        self.assertEqual(
            sorted(
                entry.line_ids.mapped(lambda line: (line.account_id.id, line.balance))
            ),
            sorted([(self.payable.id, 60.0), (self.advances.id, -60.0)]),
        )
        self.assertFalse(entry.payment_ids)
        self.assertTrue(advance.reconciled)
        self.assertEqual(bill.payment_state, "partial")
        self.assertEqual(bill.amount_residual, 40.0)

    def test_a_third_party_payment_moves_the_bill_to_its_account(self):
        bill = self._bill(100.0)

        wizard = self._wizard(bill, source="account", account_id=self.third_party.id)
        wizard.action_apply()

        self.assertIn(bill.payment_state, ("paid", "in_payment"))
        entry = bill.line_ids.matched_debit_ids.debit_move_id.move_id
        self.assertEqual(
            sorted(
                entry.line_ids.mapped(lambda line: (line.account_id.id, line.balance))
            ),
            sorted([(self.payable.id, 100.0), (self.third_party.id, -100.0)]),
        )
