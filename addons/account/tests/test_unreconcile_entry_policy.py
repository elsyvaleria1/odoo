from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestUnreconcileEntryPolicy(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receivable_account = cls.company_data["default_account_receivable"]
        cls.transition_account = cls.env["account.account"].create(
            {
                "code": "unrec.transition",
                "name": "Unreconciliation tax transition",
                "account_type": "liability_current",
                "reconcile": True,
            }
        )
        cls.cash_tax = cls.tax_sale_a.copy(
            {
                "name": "Unreconciliation cash tax",
                "type_tax_use": "none",
                "tax_exigibility": "on_payment",
                "cash_basis_transition_account_id": cls.transition_account.id,
            }
        )
        cls.company_data["company"].account_config_id.write(
            {
                "tax_exigibility": True,
                "tax_cash_basis_journal_id": cls.company_data[
                    "default_journal_misc"
                ].id,
                "account_cash_basis_base_account_id": cls.company_data[
                    "default_account_revenue"
                ].id,
            }
        )

    def _use_deletion_policy(self):
        self.startPatcher(
            patch.object(
                type(self.env["account.move"]),
                "_get_unreconcile_entry_policy",
                return_value="delete_if_allowed",
            )
        )

    def _paid_document(self, move_type="out_invoice", post=True):
        invoice = self.init_invoice(
            move_type,
            amounts=[1000.0],
            taxes=self.cash_tax,
            post=post,
        )
        result = self.pay_with_statement_line(
            invoice,
            self.company_data["default_journal_bank"].id,
            "2019-01-02",
            invoice.amount_total
            if move_type == "out_invoice"
            else -invoice.amount_total,
        )
        payment_line = result["statement_line_reconciled"]
        caba = invoice.tax_cash_basis_created_move_ids
        self.assertEqual(len(caba), 1)
        self.assertEqual(caba.state, "posted" if post else "draft")
        return invoice, payment_line, caba

    def test_default_policy_preserves_history(self):
        invoice, payment_line, caba = self._paid_document()
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertEqual(invoice.amount_residual, invoice.amount_total)

    def test_draft_automatic_entry_is_deleted_under_default_policy(self):
        invoice, payment_line, caba = self._paid_document(post=False)
        self.assertFalse(caba.posted_before)
        invoice.company_id.account_config_id.fiscalyear_lock_date = fields.Date.to_date(
            "2019-01-02"
        )
        payment_line.remove_move_reconcile()
        self.assertFalse(caba.exists())
        self.assertEqual(invoice.amount_residual, invoice.amount_total)

    def test_delete_policy_updates_tax_matching_numbers(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        tax_lines = invoice.line_ids.filtered(
            lambda line: line.account_id == self.transition_account
        )
        self.assertTrue(tax_lines.matching_number)
        payment_line.remove_move_reconcile()
        self.assertFalse(caba.exists())
        self.assertFalse(tax_lines.full_reconcile_id)
        self.assertFalse(tax_lines.matched_debit_ids | tax_lines.matched_credit_ids)
        self.assertFalse(tax_lines.matching_number)
        self.assertFalse(payment_line.matching_number)

    def test_audit_trail_falls_back_to_reversal(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        invoice.company_id.account_config_id.restrictive_audit_trail = True
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertEqual(invoice.amount_residual, invoice.amount_total)

    def test_hash_falls_back_to_reversal(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        caba.button_hash()
        original_hash = caba.inalterable_hash
        self.assertTrue(original_hash)
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.inalterable_hash, original_hash)
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertEqual(invoice.amount_residual, invoice.amount_total)

    def test_locked_period_falls_back_to_reversal(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        lock_date = fields.Date.to_date("2019-01-02")
        invoice.company_id.account_config_id.fiscalyear_lock_date = lock_date
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertGreater(caba.reversal_move_ids.date, lock_date)

    def test_hard_lock_falls_back_to_reversal(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        lock_date = fields.Date.to_date("2019-01-02")
        invoice.company_id.account_config_id.hard_lock_date = lock_date
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertGreater(caba.reversal_move_ids.date, lock_date)

    def test_tax_lock_falls_back_to_reversal(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        lock_date = fields.Date.to_date("2019-01-02")
        invoice.company_id.account_config_id.tax_lock_date = lock_date
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertGreater(caba.reversal_move_ids.date, lock_date)

    def test_sequence_protection_falls_back_to_reversal(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        accountant = new_test_user(
            self.env,
            login="unreconcile_accountant",
            groups="account.group_account_user",
            company_id=invoice.company_id.id,
        )
        self.create_line_for_reconciliation(
            100, 100, self.env.company.currency_id, "2019-01-03"
        )
        self.assertFalse(caba.with_user(accountant)._can_unlink_sequence_chain())

        payment_line.with_user(accountant).remove_move_reconcile()

        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertEqual(invoice.amount_residual, invoice.amount_total)

    def test_customer_payment_can_be_reassigned(self):
        self._assert_payment_reassignment("out_invoice")

    def test_vendor_payment_can_be_reassigned(self):
        self._assert_payment_reassignment("in_invoice")

    def _assert_payment_reassignment(self, move_type):
        self._use_deletion_policy()
        original, payment_line, caba = self._paid_document(move_type)
        replacement = self.init_invoice(
            move_type, amounts=[1000.0], taxes=self.cash_tax, post=True
        )
        payment = payment_line.move_id
        payment_line.remove_move_reconcile()
        replacement_lines = replacement.line_ids.filtered(
            lambda line: line.account_id == payment_line.account_id
        )
        (payment_line | replacement_lines).reconcile()
        self.assertFalse(caba.exists())
        self.assertEqual(original.amount_residual, original.amount_total)
        self.assertEqual(replacement.amount_residual, 0.0)
        self.assertEqual(payment_line.move_id, payment)
        self.assertEqual(len(replacement.tax_cash_basis_created_move_ids), 1)
        self.assertEqual(replacement.tax_cash_basis_created_move_ids.state, "posted")

    def test_deletion_failure_rolls_back_unreconciliation(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        partials = payment_line.matched_debit_ids | payment_line.matched_credit_ids
        full = payment_line.full_reconcile_id
        dependent = caba.line_ids.matched_debit_ids | caba.line_ids.matched_credit_ids
        self.assertTrue(dependent)
        partial_model = type(partials)
        original_unlink = partial_model.unlink

        def reject_dependent(records):
            if records & dependent:
                raise UserError("Dependent reconciliation veto")
            return original_unlink(records)

        with (
            patch.object(partial_model, "unlink", reject_dependent),
            self.assertRaisesRegex(UserError, "Dependent reconciliation veto"),
        ):
            payment_line.remove_move_reconcile()
        self.assertEqual(partials.exists(), partials)
        self.assertTrue(full.exists())
        self.assertTrue(caba.exists())
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(payment_line.full_reconcile_id, full)

    def test_forged_deletion_context_cannot_delete_posted_lines(self):
        invoice, payment_line, caba = self._paid_document()
        with self.assertRaises(UserError), self.cr.savepoint():
            caba.with_context(
                unreconcile_entry_deletion=True,
                unreconcile_entry_ids=caba.ids,
            ).unlink()
        self.assertTrue(caba.exists())
        self.assertTrue(payment_line.reconciled)
        self.assertEqual(invoice.amount_residual, 0.0)

    def _create_shared_exchange_reconciliation(self):
        currency = self.setup_other_currency("EUR")
        debits = self.env["account.move.line"]
        credits = self.env["account.move.line"]
        for _index in range(2):
            debits |= self.create_line_for_reconciliation(
                100, 100, currency, "2019-01-01"
            )
            credits |= self.create_line_for_reconciliation(
                -110, -100, currency, "2019-01-02"
            )
        exchange = self.env["account.move"].create(
            {
                "date": "2019-01-02",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.receivable_account.id,
                            "balance": 10.0,
                            "currency_id": currency.id,
                            "amount_currency": 0.0,
                        }
                    )
                    for _index in range(2)
                ]
                + [
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": -20.0,
                        }
                    )
                ],
            }
        )
        exchange.action_post()
        owners = self.env["account.partial.reconcile"].create(
            [
                {
                    "debit_move_id": debit.id,
                    "credit_move_id": credit.id,
                    "amount": 100.0,
                    "debit_amount_currency": 100.0,
                    "credit_amount_currency": 100.0,
                    "exchange_move_id": exchange.id,
                }
                for debit, credit in zip(debits, credits, strict=True)
            ]
        )
        exchange_lines = exchange.line_ids.filtered(
            lambda line: line.account_id == self.receivable_account
        )
        self.env["account.partial.reconcile"].create(
            [
                {
                    "debit_move_id": line.id,
                    "credit_move_id": credit.id,
                    "amount": 10.0,
                    "debit_amount_currency": 0.0,
                    "credit_amount_currency": 0.0,
                }
                for line, credit in zip(exchange_lines, credits, strict=True)
            ]
        )
        self.assertTrue(all((debits | credits).mapped("reconciled")))
        return owners, exchange, debits, credits

    def test_shared_exchange_requires_all_owners_to_be_unreconciled(self):
        self._use_deletion_policy()
        owners, exchange, debits, credits = (
            self._create_shared_exchange_reconciliation()
        )
        with self.assertRaisesRegex(UserError, "shared by multiple reconciliations"):
            owners[0].unlink()
        self.assertEqual(owners.exists(), owners)
        self.assertTrue(all((debits | credits).mapped("reconciled")))
        self.assertEqual(exchange.exchange_diff_partial_ids, owners)

    def test_shared_exchange_batch_deletion_restores_balances(self):
        self._use_deletion_policy()
        owners, exchange, debits, credits = (
            self._create_shared_exchange_reconciliation()
        )
        owners.unlink()
        self.assertFalse(exchange.exists())
        for line in debits | credits:
            self.assertEqual(line.amount_residual, line.balance)
            self.assertEqual(line.amount_residual_currency, line.amount_currency)
            self.assertFalse(line.matching_number)

    def test_shared_exchange_batch_reversal_restores_balances(self):
        owners, exchange, debits, credits = (
            self._create_shared_exchange_reconciliation()
        )
        owners.unlink()
        self.assertTrue(exchange.exists())
        self.assertEqual(exchange.reversal_move_ids.state, "posted")
        for line in debits | credits:
            self.assertEqual(line.amount_residual, line.balance)
            self.assertEqual(line.amount_residual_currency, line.amount_currency)
            self.assertFalse(line.matching_number)

    def test_hidden_cash_basis_entry_blocks_unreconciliation(self):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        partials = payment_line.matched_debit_ids | payment_line.matched_credit_ids
        accountant = new_test_user(
            self.env,
            login="unreconcile_hidden_caba",
            groups="account.group_account_user",
            company_id=invoice.company_id.id,
        )
        self.env["ir.access"].create(
            {
                "name": "Hide automatic cash basis entries",
                "model_id": self.env["ir.model"]._get_id("account.move"),
                "group_id": self.env.ref("account.group_account_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": "[('tax_cash_basis_origin_move_id', '=', False)]",
            }
        )
        self.assertFalse(caba.with_user(accountant).has_access("read"))
        with self.assertRaises(AccessError):
            payment_line.with_user(accountant).remove_move_reconcile()
        self.assertTrue(partials.exists())
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_hidden_exchange_owner_cannot_be_bypassed(self):
        self._use_deletion_policy()
        owners, exchange, debits, credits = (
            self._create_shared_exchange_reconciliation()
        )
        accountant = new_test_user(
            self.env,
            login="unreconcile_hidden_owner",
            groups="account.group_account_user",
            company_id=self.env.company.id,
        )
        self.env["ir.access"].create(
            {
                "name": "Hide a shared exchange owner",
                "model_id": self.env["ir.model"]._get_id("account.partial.reconcile"),
                "group_id": self.env.ref("account.group_account_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": repr([("id", "!=", owners[1].id)]),
            }
        )
        self.assertFalse(owners[1].with_user(accountant).has_access("read"))
        with self.assertRaisesRegex(UserError, "shared by multiple reconciliations"):
            owners[0].with_user(accountant).unlink()
        self.assertEqual(owners.exists(), owners)
        self.assertTrue(exchange.exists())
        self.assertTrue(all((debits | credits).mapped("reconciled")))

    def _assert_delete_denial_uses_reversal(self, model_name):
        self._use_deletion_policy()
        invoice, payment_line, caba = self._paid_document()
        protected = caba if model_name == "account.move" else caba.line_ids
        self.env["ir.access"].create(
            {
                "name": "Protect automatic entries from deletion",
                "model_id": self.env["ir.model"]._get_id(model_name),
                "group_id": self.env.ref("account.group_account_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "d",
                "domain": repr([("id", "not in", protected.ids)]),
            }
        )
        self.assertFalse(protected.has_access("unlink"))
        payment_line.remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(caba.reversal_move_ids.state, "posted")
        self.assertEqual(invoice.amount_residual, invoice.amount_total)

    def test_move_delete_denial_falls_back_to_reversal(self):
        self._assert_delete_denial_uses_reversal("account.move")

    def test_line_delete_denial_falls_back_to_reversal(self):
        self._assert_delete_denial_uses_reversal("account.move.line")

    def test_draft_delete_denial_does_not_post_a_reversal(self):
        invoice, payment_line, caba = self._paid_document(post=False)
        partials = payment_line.matched_debit_ids | payment_line.matched_credit_ids
        self.env["ir.access"].create(
            {
                "name": "Protect draft cash basis entry",
                "model_id": self.env["ir.model"]._get_id("account.move"),
                "group_id": self.env.ref("account.group_account_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "d",
                "domain": repr([("id", "!=", caba.id)]),
            }
        )
        with self.assertRaises(AccessError):
            payment_line.remove_move_reconcile()
        self.assertEqual(caba.state, "draft")
        self.assertFalse(caba.reversal_move_ids)
        self.assertEqual(partials.exists(), partials)
        self.assertEqual(invoice.amount_residual, 0.0)

    def _assert_hidden_lines_block_unreconciliation(self, deletion_policy):
        if deletion_policy:
            self._use_deletion_policy()
        self.transition_account.reconcile = False
        invoice, payment_line, caba = self._paid_document()
        partials = payment_line.matched_debit_ids | payment_line.matched_credit_ids
        hidden_lines = caba.line_ids.filtered(
            lambda line: line.account_id != self.company_data["default_account_revenue"]
        )
        self.assertEqual(len(hidden_lines), 2)
        self.assertEqual(sum(hidden_lines.mapped("balance")), 0.0)
        accountant = new_test_user(
            self.env,
            login="unreconcile_hidden_tax_lines",
            groups="account.group_account_manager,account.group_account_user",
            company_id=invoice.company_id.id,
        )
        self.env["ir.access"].create(
            {
                "name": "Hide the tax pair in a cash basis entry",
                "model_id": self.env["ir.model"]._get_id("account.move.line"),
                "group_id": self.env.ref("account.group_account_user").id,
                "kind": "guard",
                "guard_scope": "members",
                "operation": "r",
                "domain": repr([("id", "not in", hidden_lines.ids)]),
            }
        )
        self.assertFalse(hidden_lines.with_user(accountant).has_access("read"))
        caba.invalidate_recordset(["line_ids"])
        self.assertEqual(len(caba.with_user(accountant).line_ids), 2)
        with self.assertRaises(AccessError):
            payment_line.with_user(accountant).remove_move_reconcile()
        self.assertTrue(caba.exists())
        self.assertEqual(partials.exists(), partials)
        self.assertEqual(invoice.amount_residual, 0.0)

    def test_hidden_cash_basis_lines_block_deletion(self):
        self._assert_hidden_lines_block_unreconciliation(deletion_policy=True)

    def test_hidden_cash_basis_lines_block_reversal(self):
        self._assert_hidden_lines_block_unreconciliation(deletion_policy=False)
