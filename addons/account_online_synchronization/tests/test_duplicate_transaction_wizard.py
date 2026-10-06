from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDuplicateTransactionWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.env["account.journal"].create(
            {"name": "Sync Bank", "type": "bank", "code": "SYNB"}
        )

    def _line(self, ref, amount, day):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal.id,
                "payment_ref": ref,
                "amount": amount,
                "date": date(2026, 7, day),
            }
        )

    def test_display_name_carries_journal(self):
        """Check the wizard display name embeds the journal name."""
        wizard = self.env["wizard.account.bank.statement.line.delete.duplicate"].create(
            {"journal_id": self.journal.id, "date": date(2026, 7, 1)}
        )
        self.assertIn("Sync Bank", wizard.display_name)

    def test_default_date_uses_oldest_of_last_batch(self):
        """Check the starting date defaults to the oldest transaction date of
        the last sync batch."""
        # all suite data shares the 10-minute create window — make our line
        # the unambiguous oldest of the batch
        self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal.id,
                "payment_ref": "BATCH-OLDEST",
                "amount": 30.0,
                "date": date(1999, 1, 1),
            }
        )
        wizard = self.env["wizard.account.bank.statement.line.delete.duplicate"].create(
            {}
        )
        self.assertEqual(wizard.date, date(1999, 1, 1))

    def test_duplicate_groups_are_flattened_once(self):
        """Check that identical transactions group as duplicates while the
        distinct one stays out."""
        dup_1 = self._line("COFFEE", 10.0, 10)
        dup_2 = self._line("COFFEE", 10.0, 10)
        other = self._line("RENT", 500.0, 11)

        wizard = self.env["wizard.account.bank.statement.line.delete.duplicate"].create(
            {"journal_id": self.journal.id, "date": date(2026, 7, 1)}
        )
        self.assertEqual(set(wizard.transaction_ids.ids), {dup_1.id, dup_2.id})
        self.assertNotIn(other.id, wizard.transaction_ids.ids)
        self.assertEqual(len(wizard.first_ids_in_group), 1)
