from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMergePartner(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Partner = cls.env["res.partner"]
        cls.Bank = cls.env["res.partner.bank.account"]
        cls.Payment = cls.env["account.payment"]

        cls.partner1 = cls.Partner.create(
            {"name": "Partner 1", "email": "partner1@example.com"}
        )
        cls.partner2 = cls.Partner.create(
            {"name": "Partner 2", "email": "partner2@example.com"}
        )
        cls.partner3 = cls.Partner.create(
            {"name": "Partner 3", "email": "partner3@example.com"}
        )

        cls.bank1 = cls.Bank.create(
            {"acc_number": "12345", "partner_id": cls.partner1.id}
        )
        cls.bank2 = cls.Bank.create(
            {"acc_number": "67890", "partner_id": cls.partner2.id}
        )
        cls.bank3 = cls.Bank.create(
            {"acc_number": "12345", "partner_id": cls.partner3.id}
        )

        cls.payment1 = cls.Payment.create(
            {
                "partner_id": cls.partner1.id,
                "bank_account_id": cls.bank1.id,
                "amount": 100,
                "payment_type": "outbound",
                "payment_method_id": cls.env.ref(
                    "account.account_payment_method_manual_out"
                ).id,
                "journal_id": cls.company_data["default_journal_bank"].id,
            }
        )
        cls.payment2 = cls.Payment.create(
            {
                "partner_id": cls.partner2.id,
                "bank_account_id": cls.bank2.id,
                "amount": 200,
                "payment_type": "outbound",
                "payment_method_id": cls.env.ref(
                    "account.account_payment_method_manual_out"
                ).id,
                "journal_id": cls.company_data["default_journal_bank"].id,
            }
        )
        cls.payment3 = cls.Payment.create(
            {
                "partner_id": cls.partner3.id,
                "bank_account_id": cls.bank3.id,
                "amount": 200,
                "payment_type": "outbound",
                "payment_method_id": cls.env.ref(
                    "account.account_payment_method_manual_out"
                ).id,
                "journal_id": cls.company_data["default_journal_bank"].id,
            }
        )

    def test_merge_partners_with_bank_accounts_linked_to_payments(self):
        wizard = self.env["wizard.res.partner.merge"].create({})
        wizard._merge([self.partner1.id, self.partner2.id], self.partner1)

        self.assertFalse(
            self.partner2.exists(), "Source partner should be deleted after merge"
        )
        self.assertTrue(
            self.partner1.exists(), "Destination partner should exist after merge"
        )
        self.assertEqual(
            self.payment1.partner_id,
            self.partner1,
            "Payment should be linked to the destination partner",
        )
        self.assertEqual(
            self.payment2.partner_id,
            self.partner1,
            "Payment should be linked to the destination partner",
        )
        self.assertEqual(
            self.payment1.bank_account_id.partner_id,
            self.partner1,
            "Payment's bank account should belong to the destination partner",
        )
        self.assertEqual(
            self.payment2.bank_account_id.partner_id,
            self.partner1,
            "Payment's bank account should belong to the destination partner",
        )

    def test_merge_partners_with_duplicate_bank_accounts_linked_to_payments(self):
        wizard = self.env["wizard.res.partner.merge"].create({})
        wizard._merge([self.partner1.id, self.partner3.id], self.partner1)

        self.assertFalse(
            self.partner3.exists(), "Source partner should be deleted after merge"
        )
        self.assertTrue(
            self.partner1.exists(), "Destination partner should exist after merge"
        )
        self.assertEqual(
            self.payment1.partner_id,
            self.partner1,
            "Payment should be linked to the destination partner",
        )
        self.assertEqual(
            self.payment3.partner_id,
            self.partner1,
            "Payment should be linked to the destination partner",
        )
        self.assertEqual(
            self.payment1.bank_account_id.partner_id,
            self.partner1,
            "Payment's bank account should belong to the destination partner",
        )
        self.assertEqual(
            self.payment3.bank_account_id.partner_id,
            self.partner1,
            "Payment's bank account should belong to the destination partner",
        )

    def test_merging_a_partner_whose_archived_account_a_payment_names(self):
        self.bank2.action_archive()
        wizard = self.env["wizard.res.partner.merge"].create({})
        wizard._merge([self.partner1.id, self.partner2.id], self.partner1)

        self.assertFalse(self.partner2.exists())
        self.assertEqual(self.payment2.bank_account_id, self.bank2)
        self.assertEqual(self.bank2.partner_id, self.partner1)

    def test_merging_without_absorbing_keeps_the_accounts_payments_name(self):
        wizard = self.env["wizard.res.partner.merge"].create(
            {"absorb_source_values": False}
        )
        wizard._merge([self.partner1.id, self.partner2.id], self.partner1)

        self.assertFalse(self.partner2.exists())
        self.assertEqual(self.payment2.bank_account_id.partner_id, self.partner1)

    def test_merging_leaves_a_posted_bill_as_it_was_posted(self):
        term = self.env.ref("payment_term.account_payment_term_30days")
        self.partner1.property_supplier_payment_term_id = self.env.ref(
            "payment_term.account_payment_term_immediate"
        )
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner2.id,
                "invoice_date": "2026-01-01",
                "bank_account_id": self.bank2.id,
                "invoice_payment_term_id": term.id,
                "invoice_line_ids": [
                    Command.create({"name": "line", "quantity": 1, "price_unit": 10})
                ],
            }
        )
        bill.action_post()
        wizard = self.env["wizard.res.partner.merge"].create({})
        wizard._merge([self.partner1.id, self.partner2.id], self.partner1)
        self.env.flush_all()
        self.env.invalidate_all()

        self.assertEqual(bill.partner_id, self.partner1)
        self.assertEqual(bill.bank_account_id, self.bank2)
        self.assertEqual(bill.invoice_payment_term_id, term)

    def _hashed_invoice(self, partner):
        self.company_data["default_journal_sale"].restrict_mode_hash_table = True
        invoice = self.init_invoice(
            "out_invoice", partner, "2026-01-01", amounts=[100], post=True
        )
        self.assertTrue(invoice.inalterable_hash)
        return invoice

    def _integrity_status(self, move):
        results = move.company_id._check_hash_integrity()["results"]
        return next(
            r["status"]
            for r in results
            if f"({move.sequence_prefix}...)" in r["journal_name"]
        )

    def test_merging_away_a_partner_of_a_hashed_entry_is_refused(self):
        invoice = self._hashed_invoice(self.partner2)
        wizard = (
            self.env["wizard.res.partner.merge"]
            .with_context(
                active_model="res.partner",
                active_ids=[self.partner1.id, self.partner2.id],
            )
            .create({"dst_partner_id": self.partner1.id})
        )

        with self.assertRaisesRegex(UserError, "used in hashed entries"):
            wizard.action_merge()

        self.assertTrue(self.partner2.exists())
        self.assertEqual(invoice.line_ids.partner_id, self.partner2)
        self.assertEqual(self._integrity_status(invoice), "verified")

    def test_automatic_merge_skips_a_group_holding_a_hashed_entry(self):
        self.partner2.email = self.partner1.email
        invoice = self._hashed_invoice(self.partner1)
        self._hashed_invoice(self.partner2)
        wizard = self.env["wizard.res.partner.merge"].create({"group_by_email": True})

        with patch.object(self.env.cr, "commit"):
            wizard.action_start_automatic_process()

        self.assertTrue(self.partner1.exists())
        self.assertTrue(self.partner2.exists())
        self.assertEqual(self._integrity_status(invoice), "verified")

    def test_merging_into_a_partner_of_a_hashed_entry_leaves_it_verified(self):
        invoice = self._hashed_invoice(self.partner1)
        wizard = self.env["wizard.res.partner.merge"].create({})

        wizard._merge([self.partner1.id, self.partner2.id], self.partner1)

        self.assertFalse(self.partner2.exists())
        self.assertEqual(invoice.line_ids.partner_id, self.partner1)
        self.assertEqual(self._integrity_status(invoice), "verified")
