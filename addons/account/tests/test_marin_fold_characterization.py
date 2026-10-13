from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon
from odoo.addons.account.tests.test_account_pending_match import PendingMatchCommon


@tagged("post_install", "-at_install")
class TestMarinFoldMoveHooks(AccountTestInvoicingCommon):
    def _record(self, events, name, method):
        def recorder(records, *args, **kwargs):
            events.append(name)
            return method(records, *args, **kwargs)

        return recorder

    def test_unlinking_a_closing_entry_posts_on_its_return(self):
        company = self.company_data["company"]
        return_type = self.env["account.return.type"].create(
            {
                "name": "Fold Return",
                "report_id": self.env.ref("account.generic_tax_report").id,
            }
        )
        tax_return = self.env["account.return"].create(
            {
                "name": "Fold Return 2019",
                "type_id": return_type.id,
                "company_id": company.id,
                "date_from": "2019-01-01",
                "date_to": "2019-01-31",
            }
        )
        closing = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-31",
                "closing_return_id": tax_return.id,
            }
        )

        closing.unlink()

        self.assertIn(
            "Closing entry deleted",
            tax_return.message_ids[:1].body,
            "deleting a closing entry leaves a note on its return",
        )

    def test_posting_runs_auto_reconcile_then_deferrals_then_audit_status(self):
        move_class = self.registry["account.move"]
        events = []
        invoice = self.init_invoice("out_invoice", amounts=[100.0], post=False)
        with (
            patch.object(
                move_class,
                "_trigger_statement_line_auto_reconcile",
                self._record(
                    events,
                    "auto_reconcile",
                    move_class._trigger_statement_line_auto_reconcile,
                ),
            ),
            patch.object(
                move_class,
                "_get_deferred_entries_method",
                self._record(
                    events, "deferrals", move_class._get_deferred_entries_method
                ),
            ),
            patch.object(
                move_class,
                "_update_accounts_audit_status",
                self._record(
                    events, "audit_status", move_class._update_accounts_audit_status
                ),
            ),
        ):
            invoice.action_post()

        self.assertEqual(events, ["auto_reconcile", "deferrals", "audit_status"])

    def test_draft_reset_reports_the_grouped_deferral_before_the_state(self):
        first = self.init_invoice("in_invoice", amounts=[100.0], post=False)
        second = self.init_invoice("in_invoice", amounts=[200.0], post=False)
        self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-31",
                "deferred_original_move_ids": [Command.set((first | second).ids)],
            }
        )

        with self.assertRaisesRegex(UserError, "grouped in deferral entry"):
            first.action_draft()

    def test_edi_creation_runs_the_name_prediction_on_new_lines_after(self):
        line_class = self.registry["account.move.line"]
        predicted = []
        seen_flags = []

        def record_prediction(lines):
            predicted.extend(lines.ids)

        with patch.object(line_class, "_onchange_name_predictive", record_prediction):
            with (
                self.env["account.move"]
                .with_context(default_move_type="in_invoice")
                ._open_edi_creation() as move
            ):
                seen_flags.append(
                    move.env.context.get("disable_onchange_name_predictive")
                )
                move.write(
                    {
                        "partner_id": self.partner_a.id,
                        "invoice_line_ids": [
                            Command.create({"name": "predict me", "price_unit": 10.0})
                        ],
                    }
                )
                self.assertFalse(predicted, "no prediction inside the block")

        self.assertEqual(seen_flags, [True])
        self.assertEqual(predicted, move.invoice_line_ids.ids)

    def _record_ids(self, events, name, method):
        def recorder(records, *args, **kwargs):
            if records:
                events.append((name, tuple(records.ids)))
            return method(records, *args, **kwargs)

        return recorder

    def test_draft_reset_reverses_deferrals_then_checks_then_resets_audit_status(self):
        move_class = self.registry["account.move"]
        events = []
        posted = self.init_invoice("out_invoice", amounts=[100.0], post=True)
        cancelled = self.init_invoice("out_invoice", amounts=[50.0], post=False)
        cancelled.action_cancel()
        moves = posted | cancelled
        with (
            patch.object(
                move_class,
                "_unlink_or_reverse",
                self._record(events, "deferrals", move_class._unlink_or_reverse),
            ),
            patch.object(
                move_class,
                "_check_draftable",
                self._record(events, "checks", move_class._check_draftable),
            ),
            patch.object(
                move_class,
                "_update_accounts_audit_status",
                self._record_ids(
                    events, "audit_status", move_class._update_accounts_audit_status
                ),
            ),
        ):
            moves.action_draft()

        self.assertEqual(
            events, ["deferrals", "checks", ("audit_status", tuple(posted.ids))]
        )
        self.assertEqual(set(moves.mapped("state")), {"draft"})

    def test_unlinking_notes_closings_then_reverses_deferrals_then_drops_the_rest(
        self,
    ):
        company = self.company_data["company"]
        company.account_config_id.restrictive_audit_trail = True
        move_class = self.registry["account.move"]
        return_class = self.registry["account.return"]
        events = []
        tax_return = self.env["account.return"].create(
            {
                "name": "Fold Return 2019",
                "type_id": self.env["account.return.type"]
                .create(
                    {
                        "name": "Fold Return",
                        "report_id": self.env.ref("account.generic_tax_report").id,
                    }
                )
                .id,
                "company_id": company.id,
                "date_from": "2019-01-01",
                "date_to": "2019-01-31",
            }
        )
        original = self.init_invoice("out_invoice", amounts=[100.0], post=False)
        deferral = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-31",
                "deferred_original_move_ids": [Command.set(original.ids)],
            }
        )
        deferral.posted_before = True
        closing = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-31",
                "closing_return_id": tax_return.id,
            }
        )

        def record_reverse(records, *args, **kwargs):
            events.append(("reverse", tuple(records.ids)))
            return records.browse()

        with (
            patch.object(
                return_class,
                "message_post",
                self._record(events, "closing_note", return_class.message_post),
            ),
            patch.object(move_class, "_reverse_moves", record_reverse),
            patch.object(
                move_class,
                "_update_sequence_made_gap",
                self._record_ids(
                    events, "unlink_body", move_class._update_sequence_made_gap
                ),
            ),
        ):
            (closing | deferral).unlink()

        self.assertEqual(
            events,
            [
                "closing_note",
                ("reverse", tuple(deferral.ids)),
                ("unlink_body", tuple(closing.ids)),
            ],
        )
        self.assertFalse(closing.exists())
        self.assertTrue(deferral.exists())
        self.assertFalse(original.deferred_move_ids)


@tagged("post_install", "-at_install")
class TestMarinFoldJournalHooks(AccountTestInvoicingCommon):
    def test_bank_journal_open_action_opens_the_matching_widget(self):
        bank = self.company_data["default_journal_bank"]

        action = bank.open_action()

        self.assertEqual(action["res_model"], "account.bank.statement.line")
        self.assertEqual(action["context"]["default_journal_id"], bank.id)

    def test_bank_journal_open_action_with_an_action_name_uses_it(self):
        bank = self.company_data["default_journal_bank"]

        action = bank.with_context(action_name="action_move_journal_line").open_action()

        self.assertEqual(action["res_model"], "account.move")

    def test_sale_journal_open_action_lists_its_invoices(self):
        sale = self.company_data["default_journal_sale"]

        action = sale.open_action()

        self.assertEqual(action["res_model"], "account.move")
        self.assertEqual(action["context"]["default_journal_id"], sale.id)

    def test_invalid_statements_open_the_widget_unless_a_statement_has_no_lines(self):
        bank = self.company_data["default_journal_bank"]

        action = bank.open_invalid_statements_action()
        self.assertEqual(action["res_model"], "account.bank.statement.line")
        self.assertTrue(action["context"]["search_default_invalid_statement"])

        empty = self.env["account.bank.statement"].create({"name": "Empty"})
        empty.flush_recordset()
        self.env.cr.execute(
            "UPDATE account_bank_statement SET journal_id = %s WHERE id = %s",
            (bank.id, empty.id),
        )
        empty.invalidate_recordset(["journal_id"])
        action = bank.open_invalid_statements_action()
        self.assertEqual(action["res_model"], "account.bank.statement")

    def test_the_return_journal_tile_carries_the_return_flags(self):
        config = self.company_data["company"].account_config_id
        return_journal = self.company_data["default_journal_misc"]
        other = self.env["account.journal"].create(
            {"name": "Other misc", "code": "OMSC", "type": "general"}
        )
        config.account_tax_return_journal_id = return_journal
        config.account_opening_date = False

        data = (return_journal | other)._get_journal_dashboard_data_batched()

        self.assertTrue(data[return_journal.id]["is_account_return_journal"])
        self.assertTrue(data[return_journal.id]["tax_return_button_primary"])
        self.assertIn("drag_drop_settings", data[return_journal.id])
        self.assertFalse(data[other.id]["is_account_return_journal"])
        self.assertNotIn("tax_return_button_primary", data[other.id])


@tagged("post_install", "-at_install")
class TestMarinFoldStatementHooks(TestBankRecWidgetCommon):
    def test_statement_line_create_hooks_see_the_caller_env(self):
        st_line_class = self.registry["account.bank.statement.line"]
        contexts = []
        original = st_line_class._set_partner_from_transaction

        def record_context(st_lines):
            contexts.append(dict(st_lines.env.context))
            return original(st_lines)

        with patch.object(
            st_line_class, "_set_partner_from_transaction", record_context
        ):
            st_line = (
                self.env["account.bank.statement.line"]
                .with_context(fold_marker=True)
                .create(
                    {
                        "amount": 100.0,
                        "date": "2019-01-01",
                        "payment_ref": "fold",
                        "journal_id": self.company_data["default_journal_bank"].id,
                    }
                )
            )

        self.assertEqual(len(contexts), 1)
        self.assertTrue(contexts[0].get("fold_marker"))
        self.assertNotIn("is_statement_line", contexts[0])
        self.assertNotIn("is_statement_line", st_line.env.context)

    def test_a_second_liquidity_line_breaks_the_statement_entry(self):
        st_line = self._create_st_line(100.0)

        with self.assertRaisesRegex(
            UserError, "exactly one journal item involving the bank/cash account"
        ):
            self.env["account.move.line"].with_context(entry_owner_sync=True).create(
                [
                    {
                        "move_id": st_line.move_id.id,
                        "account_id": st_line.journal_id.default_account_id.id,
                        "debit": 1.0,
                    },
                    {
                        "move_id": st_line.move_id.id,
                        "account_id": self.company_data["default_account_revenue"].id,
                        "credit": 1.0,
                    },
                ]
            )

    def test_a_second_suspense_line_breaks_the_statement_entry(self):
        st_line = self._create_st_line(100.0)

        with self.assertRaisesRegex(UserError, "exactly one suspense line"):
            self.env["account.move.line"].with_context(entry_owner_sync=True).create(
                [
                    {
                        "move_id": st_line.move_id.id,
                        "account_id": st_line.journal_id.suspense_account_id.id,
                        "debit": 1.0,
                    },
                    {
                        "move_id": st_line.move_id.id,
                        "account_id": self.company_data["default_account_revenue"].id,
                        "credit": 1.0,
                    },
                ]
            )

    def test_a_complete_statement_gets_its_pdf_unless_skipped(self):
        statement_class = self.registry["account.bank.statement"]
        generated = []

        def record_generation(statements):
            generated.append(statements.ids)

        st_line = self._create_st_line(100.0)
        with patch.object(
            statement_class, "action_generate_attachment", record_generation
        ):
            statement = self.env["account.bank.statement"].create(
                {
                    "name": "Complete",
                    "balance_start": 0.0,
                    "balance_end_real": 100.0,
                    "line_ids": [Command.set(st_line.ids)],
                }
            )
            other_line = self._create_st_line(50.0)
            self.env["account.bank.statement"].with_context(
                skip_pdf_attachment_generation=True
            ).create(
                {
                    "name": "Skipped",
                    "balance_start": 100.0,
                    "balance_end_real": 150.0,
                    "line_ids": [Command.set(other_line.ids)],
                }
            )

        self.assertTrue(statement.is_complete)
        self.assertEqual(generated, [statement.ids])


@tagged("post_install", "-at_install")
class TestMarinFoldPendingHooks(PendingMatchCommon):
    def test_rewriting_an_unchanged_sensitive_field_still_drops_lost_matches(self):
        bill = self._draft(1000.0)
        self._match_on_bank(bill)
        term = self._term(bill)
        self.assertTrue(term.pending_match_amount)
        match_class = self.registry["account.pending.match"]
        calls = []
        original = match_class._drop_lost

        def record_drop_lost(matches):
            calls.append(matches.ids)
            return original(matches)

        with patch.object(match_class, "_drop_lost", record_drop_lost):
            term.write({"partner_id": term.partner_id.id})
            term.write({"name": term.name})

        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0])
        self.assertTrue(bill.pending_match_ids, "an unchanged write loses nothing")

    def test_leaving_posted_drops_lost_matches_after_the_account_check(self):
        bill = self._draft(1000.0)
        self._match_on_bank(bill)
        line_class = self.registry["account.move.line"]
        match_class = self.registry["account.pending.match"]
        events = []

        def record(name, method):
            def recorder(records, *args, **kwargs):
                events.append(name)
                return method(records, *args, **kwargs)

            return recorder

        with (
            patch.object(
                line_class,
                "_check_account_is_usable",
                record("account_check", line_class._check_account_is_usable),
            ),
            patch.object(
                match_class, "_drop_lost", record("drop_lost", match_class._drop_lost)
            ),
        ):
            bill.write({"state": "draft", "currency_id": bill.currency_id.id})

        self.assertEqual(events[-2:], ["account_check", "drop_lost"])

    def test_unlinking_a_pending_line_releases_its_matches_before_the_checks(self):
        bill = self._draft(1000.0)
        self._match_on_bank(bill)
        term = self._term(bill)
        line_class = self.registry["account.move.line"]
        events = []

        def record(name, method):
            def recorder(records, *args, **kwargs):
                events.append(name)
                return method(records, *args, **kwargs)

            return recorder

        with (
            patch.object(
                line_class,
                "_release_pending_matches",
                record("release", line_class._release_pending_matches),
            ),
            patch.object(
                line_class,
                "_check_owned_line_unlink",
                record("owned_check", line_class._check_owned_line_unlink),
            ),
            self.assertRaises(ValidationError),
        ):
            term.unlink()

        self.assertEqual(events, ["release", "owned_check"])


@tagged("post_install", "-at_install")
class TestMarinFoldMoveLineHooks(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.company_data["company"]
        cls.tax_return = cls.env["account.return"].create(
            {
                "name": "Fold Return 2019",
                "type_id": cls.env["account.return.type"]
                .create(
                    {
                        "name": "Fold Return",
                        "report_id": cls.env.ref("account.generic_tax_report").id,
                    }
                )
                .id,
                "company_id": company.id,
                "date_from": "2019-01-01",
                "date_to": "2019-01-31",
            }
        )
        cls.taxed_account = cls.company_data["default_account_revenue"]
        cls.taxed_account.tax_ids = cls.tax_sale_a

    def _entry(self, **values):
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-31",
                "line_ids": [
                    Command.create(
                        {"account_id": self.taxed_account.id, "balance": 10.0}
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "balance": -10.0,
                        }
                    ),
                ],
                **values,
            }
        )

    def _taxed_line(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id == self.taxed_account
        )

    def test_closing_lines_never_take_taxes_and_follow_the_closing_return(self):
        closing = self._entry(closing_return_id=self.tax_return.id)
        plain = self._entry()
        lines = (self._taxed_line(closing) | self._taxed_line(plain)).with_context(
            account_default_taxes=True
        )

        lines._compute_tax_ids()

        self.assertFalse(self._taxed_line(closing).tax_ids)
        self.assertEqual(self._taxed_line(plain).tax_ids, self.tax_sale_a)
        depends = self.env.registry.field_depends[
            self.env["account.move.line"]._fields["tax_ids"]
        ]
        self.assertIn("move_id.closing_return_id", depends)
        self.assertIn("product_id", depends)

    def test_closing_lines_affect_the_tax_report(self):
        closing = self._entry(closing_return_id=self.tax_return.id)
        plain = self._entry()

        self.assertEqual(
            self._taxed_line(closing)._affect_tax_report(), self.tax_return
        )
        self.assertFalse(self._taxed_line(plain)._affect_tax_report())

    def test_deferral_lines_keep_their_own_taxes(self):
        original = self.init_invoice("out_invoice", amounts=[100.0], post=False)
        deferral = self._entry(deferred_original_move_ids=[Command.set(original.ids)])
        plain = self._entry()
        Line = self.env["account.move.line"].with_context(account_default_taxes=True)

        self.assertFalse(
            Line.browse(self._taxed_line(deferral).id)._get_computed_taxes()
        )
        self.assertEqual(
            Line.browse(self._taxed_line(plain).id)._get_computed_taxes(),
            self.tax_sale_a,
        )

    def test_closing_line_attachments_fall_back_to_the_return(self):
        line = self._taxed_line(self._entry(closing_return_id=self.tax_return.id))
        Line = self.env["account.move.line"]

        self.assertIn(
            [
                ("res_model", "=", "account.return"),
                ("res_id", "in", self.tax_return.ids),
            ],
            line._get_attachment_domains(),
        )
        self.assertEqual(
            Line._get_attachment_by_record(
                {("account.return", self.tax_return.id): "return"}, line
            ),
            "return",
        )
        self.assertEqual(
            Line._get_attachment_by_record(
                {
                    ("account.move", line.move_id.id): "move",
                    ("account.return", self.tax_return.id): "return",
                },
                line,
            ),
            "move",
        )
        self.assertIsNone(
            Line._get_attachment_by_record({}, self._taxed_line(self._entry()))
        )

    def test_reversal_copies_carry_the_deferral_dates(self):
        bill = self.init_invoice("in_invoice", amounts=[1200.0], post=False)
        line = bill.invoice_line_ids
        line.write(
            {"deferred_start_date": "2019-01-01", "deferred_end_date": "2019-12-31"}
        )

        [reversal_vals] = line.with_context(move_reverse_cancel=False).copy_data()
        [plain_vals] = line.copy_data()

        self.assertEqual(str(reversal_vals["deferred_start_date"]), "2019-01-01")
        self.assertEqual(str(reversal_vals["deferred_end_date"]), "2019-12-31")
        self.assertNotIn("deferred_start_date", plain_vals)
        self.assertNotIn("deferred_end_date", plain_vals)

    def test_statement_entries_list_the_statement_attachments(self):
        st_line = self._create_st_line(100.0)
        attachment = self.env["ir.attachment"].create(
            {"name": "statement.pdf", "raw": b"%PDF-1.4"}
        )
        self.env["account.bank.statement"].create(
            {
                "name": "With attachment",
                "line_ids": [Command.set(st_line.ids)],
                "attachment_ids": [Command.set(attachment.ids)],
            }
        )

        attachments = st_line.move_id._get_mail_thread_data_attachments()

        self.assertIn(attachment, attachments[st_line.move_id.id])
