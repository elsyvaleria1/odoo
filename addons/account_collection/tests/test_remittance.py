from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account_collection.models.account_collection_remittance import (
    bank_reference_for,
)
from odoo.addons.account_collection.tests.common import CollectionCommon


@tagged("post_install", "-at_install")
class TestRemittance(CollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice_1 = cls._post_invoice(1000.0)
        cls.invoice_2 = cls._post_invoice(500.0, partner=cls.partner_b)

    def _collect_both(self):
        return self._collect(self.invoice_1, 1000.0) | self._collect(
            self.invoice_2, 500.0
        )

    def _remit(self, journal, **vals):
        remittance = (
            self.env["account.collection.remittance"]
            .with_user(self.collector)
            .create({"destination_journal_id": journal.id, **vals})
        )
        remittance.action_load_custody()
        remittance.action_submit()
        return remittance.with_env(self.env)

    def test_cash_handed_in_to_a_till_releases_the_custody(self):
        payments = self._collect_both()

        remittance = self._remit(self.till_journal)
        self.assertEqual(remittance.state, "submitted")
        self.assertEqual(remittance.payment_ids, payments)
        self.assertEqual(remittance.amount_collected, 1500.0)
        self.assertEqual(remittance.amount_handed_in, 1500.0)

        remittance.with_user(self.treasurer).action_validate()

        self.assertEqual(remittance.state, "done")
        self.assertEqual(set(payments.mapped("state")), {"paid"})
        self.assertFalse(payments.filtered("is_in_custody"))
        self.assertEqual(set(payments.mapped("is_bank_matched")), {True})
        till_line = remittance.move_id.line_ids.filtered(
            lambda line: line.account_id == self.till_journal.default_account_id
        )
        self.assertEqual(till_line.debit, 1500.0)
        self.assertEqual(remittance.move_id.state, "posted")

    def test_a_bank_deposit_settles_the_bank_transaction(self):
        payments = self._collect_both()
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "amount": 1500.0,
                "payment_ref": "deposit 4711",
                "date": self.today,
            }
        )
        remittance = self._remit(self.bank_journal, deposit_reference="4711")
        remittance.with_user(self.treasurer).write({"statement_line_id": st_line.id})

        remittance.with_user(self.treasurer).action_validate()

        self.assertEqual(set(payments.mapped("state")), {"paid"})
        self.assertTrue(st_line.is_reconciled)

    def test_a_shortage_is_charged_to_the_collector(self):
        payments = self._collect_both()
        remittance = self._remit(self.till_journal, amount_handed_in=1400.0)
        self.assertEqual(remittance.amount_difference, -100.0)

        remittance.with_user(self.treasurer).action_validate()

        shortage = remittance.move_id.line_ids.filtered(
            lambda line: line.account_id == self.shortage_account
        )
        self.assertEqual(shortage.debit, 100.0)
        self.assertEqual(shortage.partner_id, self.collector.partner_id)
        self.assertEqual(set(payments.mapped("state")), {"paid"})

    def test_an_overage_is_credited(self):
        self._collect_both()
        remittance = self._remit(self.till_journal, amount_handed_in=1520.0)

        remittance.with_user(self.treasurer).action_validate()

        overage = remittance.move_id.line_ids.filtered(
            lambda line: line.account_id == self.overage_account
        )
        self.assertEqual(overage.credit, 20.0)

    def test_a_collector_cannot_validate_their_own_remittance(self):
        self._collect_both()
        remittance = self._remit(self.till_journal)
        with self.assertRaises(AccessError):
            remittance.with_user(self.collector).action_validate()

    def test_only_a_manager_reverts_a_handed_in_remittance(self):
        self._collect_both()
        remittance = self._remit(self.till_journal)
        remittance.with_user(self.treasurer).action_validate()
        with self.assertRaises(AccessError):
            remittance.with_user(self.treasurer).action_revert()
        with self.assertRaises(AccessError):
            remittance.with_user(self.collector).action_revert()

    def test_a_collector_cannot_hand_in_someone_elses_collection(self):
        theirs = self._collect(self.invoice_1, 1000.0, collector=self.other_collector)
        with self.assertRaises((ValidationError, AccessError)):
            self.env["account.collection.remittance"].with_user(self.collector).create(
                {
                    "destination_journal_id": self.till_journal.id,
                    "payment_ids": [(4, theirs.id)],
                }
            )

    def test_a_collection_is_handed_in_once(self):
        payments = self._collect_both()
        self._remit(self.till_journal)
        second = (
            self.env["account.collection.remittance"]
            .with_user(self.collector)
            .create({"destination_journal_id": self.till_journal.id})
        )
        second.action_load_custody()
        self.assertFalse(second.payment_ids)
        with self.assertRaises(ValidationError):
            second.payment_ids = payments

    def test_a_remitted_collection_cannot_be_reset(self):
        payments = self._collect_both()
        self._remit(self.till_journal)
        with self.assertRaises(UserError):
            payments[0].action_draft()

    def test_reverting_returns_the_collections_to_custody(self):
        payments = self._collect_both()
        remittance = self._remit(self.till_journal)
        remittance.with_user(self.treasurer).action_validate()
        entry = remittance.move_id

        remittance.action_revert()

        self.assertEqual(remittance.state, "draft")
        self.assertFalse(remittance.move_id)
        self.assertEqual(entry.reversal_move_ids.state, "posted")
        self.assertEqual(set(payments.mapped("is_bank_matched")), {False})
        self.assertTrue(all(payments.mapped("is_in_custody")))
        remittance.action_cancel()
        self.assertFalse(payments.collection_remittance_id)

    def test_a_cancelled_remittance_frees_its_collections(self):
        payments = self._collect_both()
        remittance = self._remit(self.till_journal)
        remittance.with_user(self.collector).action_cancel()
        self.assertFalse(payments.collection_remittance_id)
        again = self._remit(self.till_journal)
        self.assertEqual(again.payment_ids, payments)

    def test_the_bank_reference_carries_a_check_digit(self):
        self.assertEqual(bank_reference_for(1), "00000018")
        self.assertEqual(bank_reference_for(7992739), "79927398")

    def test_the_bank_report_validates_a_referenced_deposit(self):
        payments = self._collect_both()
        remittance = self._remit(self.bank_journal)
        number = int(remittance.bank_reference)
        unrelated = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "amount": 1500.0,
                "payment_ref": "DEPOSITO EFECTIVO REF 99999999",
                "date": self.today,
            }
        )
        deposit = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "amount": 1500.0,
                "payment_ref": f"DEPOSITO EFECTIVO REF {number}",
                "date": self.today,
            }
        )

        self.env["account.collection.remittance"]._cron_match_bank_transactions()

        self.assertEqual(remittance.state, "done")
        self.assertEqual(remittance.statement_line_id, deposit)
        self.assertTrue(deposit.is_reconciled)
        self.assertFalse(unrelated.is_reconciled)
        self.assertEqual(set(payments.mapped("is_bank_matched")), {True})

    def test_a_deposit_of_another_amount_waits_for_the_treasury(self):
        self._collect_both()
        remittance = self._remit(self.bank_journal)
        self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "amount": 1400.0,
                "payment_ref": f"DEPOSITO {remittance.bank_reference}",
                "date": self.today,
            }
        )

        self.env["account.collection.remittance"]._cron_match_bank_transactions()

        self.assertEqual(remittance.state, "submitted")
