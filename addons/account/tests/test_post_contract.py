from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account.tests.common_posting_obligation import (
    exemption_notes,
    holding_invoice_posting,
)


@tagged("post_install", "-at_install")
class TestPostContract(AccountTestInvoicingCommon):
    def _invoice(self, date, partner=None):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": (partner or self.partner_a).id,
                "invoice_date": date,
                "date": date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )

    def test_post_returns_a_subset_of_the_moves_it_was_given(self):
        today = fields.Date.context_today(self.env.user)
        same_day = self._invoice(today)
        future = self._invoice(today + timedelta(days=30))

        posted = (same_day | future)._post(soft=True)

        self.assertEqual(posted, same_day)
        self.assertFalse(posted - (same_day | future))
        self.assertEqual(future.state, "draft")
        self.assertEqual(future.auto_post, "at_date")

    def test_hard_post_returns_every_move_and_nothing_else(self):
        today = fields.Date.context_today(self.env.user)
        moves = self._invoice(today) | self._invoice(today, self.partner_b)

        posted = moves._post(soft=False)

        self.assertEqual(posted, moves)

    def test_post_entries_is_the_override_point(self):
        seen = []
        AccountMove = type(self.env["account.move"])
        original = AccountMove._post_entries

        def recording_post_entries(records):
            seen.append(records)
            return original(records)

        today = fields.Date.context_today(self.env.user)
        same_day = self._invoice(today)
        future = self._invoice(today + timedelta(days=30))

        AccountMove._post_entries = recording_post_entries
        try:
            (same_day | future)._post(soft=True)
        finally:
            AccountMove._post_entries = original

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0], same_day)

    def test_action_post_confirms_only_the_flagged_moves(self):
        today = fields.Date.context_today(self.env.user)
        clean = self._invoice(today)
        flagged = self._invoice(today, self.partner_b)
        self.env.cache.set(
            flagged, flagged._fields["abnormal_amount_warning"], "unusual"
        )
        self.env.cache.set(flagged, flagged._fields["abnormal_date_warning"], False)
        self.env.cache.set(clean, clean._fields["abnormal_amount_warning"], False)
        self.env.cache.set(clean, clean._fields["abnormal_date_warning"], False)

        action = (
            (clean | flagged)
            .with_context(disable_abnormal_invoice_detection=False)
            .action_post()
        )

        self.assertEqual(action["res_model"], "wizard.account.move.post")
        wizard = self.env["wizard.account.move.post"].browse(action["res_id"])
        self.assertEqual(wizard.move_ids, flagged)
        self.assertEqual(clean.state, "posted")
        self.assertEqual(flagged.state, "draft")

    def _record_posting_rules(self):
        calls = []
        AccountMove = type(self.env["account.move"])

        def recorder(kind):
            original = getattr(AccountMove, kind)

            def record(records):
                calls.append((kind, records))
                return original(records)

            return patch.object(AccountMove, kind, record)

        return (
            calls,
            recorder("_check_posting_integrity"),
            recorder("_check_posting_advisories"),
        )

    def _autopost(self, move):
        move.auto_post = "at_date"
        with patch.object(
            type(self.env["ir.cron"]), "_commit_progress", lambda *a, **kw: None
        ):
            self.env["account.move"]._autopost_draft_entries()

    def test_a_person_decided_posting_runs_advisories_then_integrity(self):
        today = fields.Date.context_today(self.env.user)
        calls, integrity, advisories = self._record_posting_rules()
        paths = {
            "the Post button": lambda move: move.action_post(),
            "the list-view action": lambda move: (
                move.action_post_moves_with_confirmation()
            ),
            "the confirmation wizard": lambda move: (
                self.env["wizard.account.move.post"]
                .create({"move_ids": [Command.set(move.ids)]})
                .action_post_moves()
            ),
            "the auto-post cron": self._autopost,
        }
        with integrity, advisories:
            for path, post in paths.items():
                calls.clear()
                move = self._invoice(today)
                post(move)
                self.assertEqual(move.state, "posted", path)
                self.assertEqual(
                    [kind for kind, records in calls if move in records],
                    ["_check_posting_advisories", "_check_posting_integrity"],
                    f"{path} did not run both rule classes, advisories first",
                )

    def test_a_system_posting_runs_integrity_but_no_advisory(self):
        today = fields.Date.context_today(self.env.user)
        invoice = self._invoice(today)
        invoice.action_post()
        calls, integrity, advisories = self._record_posting_rules()
        with integrity, advisories:
            reversal = invoice._reverse_moves(
                [{"invoice_date": today, "date": today}], cancel=True
            )
            self.assertEqual(reversal.state, "posted")
            direct = self._invoice(today)
            direct._post(soft=False)
            scheduled = self._invoice(today + timedelta(days=30))
            scheduled._post(soft=True)

        self.assertEqual(
            [records for kind, records in calls if kind == "_check_posting_integrity"],
            [reversal, direct, scheduled],
            "a posting that skipped the integrity rules, or a move scheduled "
            "without them",
        )
        self.assertFalse(
            [kind for kind, _records in calls if kind == "_check_posting_advisories"],
            "an advisory asks a person, and no person decided these postings",
        )

    def test_an_integrity_rule_stops_a_direct_post(self):
        today = fields.Date.context_today(self.env.user)
        AccountMove = type(self.env["account.move"])
        refused = self._invoice(today)
        scheduled = self._invoice(today + timedelta(days=30))

        def refuse(records):
            if records & (refused | scheduled):
                raise UserError("integrity")

        with patch.object(AccountMove, "_check_posting_integrity", refuse):
            with self.assertRaisesRegex(UserError, "integrity"):
                refused._post(soft=False)
            with self.assertRaisesRegex(UserError, "integrity"):
                scheduled._post(soft=True)

        self.assertEqual(refused.state, "draft")
        self.assertEqual(scheduled.auto_post, "no", "a refused move was scheduled")

    def test_an_advisory_does_not_stop_a_system_posting(self):
        today = fields.Date.context_today(self.env.user)
        AccountMove = type(self.env["account.move"])

        def refuse(records):
            raise UserError("advisory")

        invoice = self._invoice(today)
        with patch.object(AccountMove, "_check_posting_advisories", refuse):
            with self.assertRaisesRegex(UserError, "advisory"):
                self._invoice(today).action_post()
            invoice._post(soft=False)

        self.assertEqual(invoice.state, "posted")

    def test_non_deductible_names_are_built_after_the_sequence_is_assigned(self):
        today = fields.Date.context_today(self.env.user)
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": today,
                "date": today,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "quantity": 1,
                            "price_unit": 100.0,
                            "tax_ids": [Command.set(self.tax_purchase_a.ids)],
                        }
                    )
                ],
            }
        )
        bill.invoice_line_ids[0].deductible_amount = 50.0
        bill.action_post()

        non_deductible = bill.line_ids.filtered(
            lambda line: (
                line.display_type
                in ("non_deductible_product_total", "non_deductible_tax")
            )
        )
        self.assertTrue(non_deductible)
        for line in non_deductible:
            self.assertTrue(line.name.startswith(bill.name))

    def test_payment_bank_account_guard_names_the_payment_it_refuses(self):
        AccountPayment = type(self.env["account.payment"])
        original = AccountPayment._get_method_codes_needing_bank_account
        AccountPayment._get_method_codes_needing_bank_account = lambda records: [
            "manual"
        ]
        try:
            journals = self.env["account.journal"].create(
                [
                    {
                        "name": f"Bank {suffix}",
                        "type": "bank",
                        "code": f"BNK{suffix}",
                        "company_id": self.env.company.id,
                    }
                    for suffix in ("X", "Y")
                ]
            )
            payments = self.env["account.payment"].create(
                [
                    {
                        "payment_type": "outbound",
                        "partner_type": "supplier",
                        "partner_id": self.partner_a.id,
                        "amount": 100.0,
                        "journal_id": journal.id,
                        "payment_channel_id": journal.outbound_payment_channel_ids[
                            0
                        ].id,
                    }
                    for journal in journals
                ]
            )
            self.assertEqual(len(payments.payment_channel_id), 2)
            with self.assertRaises(UserError):
                payments.action_post()
        finally:
            AccountPayment._get_method_codes_needing_bank_account = original

    def test_a_move_that_cannot_post_is_not_scheduled(self):
        today = fields.Date.context_today(self.env.user)
        invoice = self._invoice(today + timedelta(days=30))
        invoice.partner_id = False

        with self.assertRaises(UserError):
            invoice._post(soft=True)

        self.assertEqual(invoice.state, "draft")
        self.assertEqual(invoice.auto_post, "no", "an invalid move was scheduled")

    def _entry(self, date):
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": date,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "balance": balance,
                        }
                    )
                    for balance in (100.0, -100.0)
                ],
            }
        )

    def test_every_posting_path_crosses_the_posting_obligation(self):
        today = fields.Date.context_today(self.env.user)
        direct = self._invoice(today)
        scheduled = self._invoice(today + timedelta(days=30))
        entry = self._entry(today)

        with holding_invoice_posting(self.env):
            with self.assertRaisesRegex(UserError, "held for approval"):
                direct._post(soft=False)
            with self.assertRaisesRegex(UserError, "held for approval"):
                scheduled._post(soft=True)
            with self.assertRaisesRegex(UserError, "held for approval"):
                self.env["wizard.account.move.post"].create(
                    {"move_ids": [Command.set(direct.ids)]}
                ).action_post_moves()
            entry._post(soft=False)

        self.assertEqual(direct.state, "draft")
        self.assertEqual(scheduled.auto_post, "no", "a held move was scheduled")
        self.assertEqual(entry.state, "posted")

    def test_a_declared_exemption_posts_and_records_what_it_let_through(self):
        today = fields.Date.context_today(self.env.user)
        invoice = self._invoice(today)
        entry = self._entry(today)

        with holding_invoice_posting(self.env):
            moves = invoice | entry
            with moves._exempting_posting_from_approval("payment_received"):
                moves._post(soft=False)

        self.assertEqual(invoice.state, "posted")
        self.assertEqual(entry.state, "posted")
        self.assertEqual(len(exemption_notes(invoice, "payment_received")), 1)
        self.assertFalse(
            exemption_notes(entry, "payment_received"),
            "nothing held the entry, so its posting waived nothing",
        )

    def test_an_exemption_admits_only_its_own_moves_and_only_while_open(self):
        today = fields.Date.context_today(self.env.user)
        exempt, other, later = (self._invoice(today) for _i in range(3))

        with holding_invoice_posting(self.env):
            with exempt._exempting_posting_from_approval("payment_received"):
                with self.assertRaisesRegex(UserError, "held for approval"):
                    other._post(soft=False)
                exempt._post(soft=False)
            with self.assertRaisesRegex(UserError, "held for approval"):
                later._post(soft=False)

        self.assertEqual(
            (exempt | other | later).mapped("state"), ["posted", "draft", "draft"]
        )

    def test_an_undeclared_exemption_is_refused(self):
        invoice = self._invoice(fields.Date.context_today(self.env.user))
        with (
            self.assertRaisesRegex(ValueError, "not a declared"),
            invoice._exempting_posting_from_approval("because_i_say_so"),
        ):
            invoice._post(soft=False)
        self.assertEqual(invoice.state, "draft")

    def test_a_cancelling_reversal_does_not_wait_for_approval(self):
        today = fields.Date.context_today(self.env.user)
        invoice = self._invoice(today)
        invoice.action_post()

        with holding_invoice_posting(self.env):
            reversal = invoice._reverse_moves(
                [{"invoice_date": today, "date": today}], cancel=True
            )

        self.assertEqual(reversal.state, "posted")
        self.assertEqual(invoice.payment_state, "reversed")
        self.assertEqual(len(exemption_notes(reversal, "reversal_cancel")), 1)

    def test_a_reversal_left_in_draft_waits_for_approval(self):
        today = fields.Date.context_today(self.env.user)
        invoice = self._invoice(today)
        invoice.action_post()

        with holding_invoice_posting(self.env):
            reversal = invoice._reverse_moves([{"invoice_date": today, "date": today}])
            with self.assertRaisesRegex(UserError, "held for approval"):
                reversal._post(soft=False)

        self.assertEqual(reversal.state, "draft")
