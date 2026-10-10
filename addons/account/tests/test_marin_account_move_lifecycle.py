from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestMarinAccountMoveLifecycle(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.misc_journal = cls.company_data["default_journal_misc"]
        cls.revenue = cls.company_data["default_account_revenue"]
        cls.expense = cls.company_data["default_account_expense"]
        cls.receivable = cls.company_data["default_account_receivable"]

    def _entry(self, lines, date="2024-01-15", **vals):
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.misc_journal.id,
                "date": date,
                "line_ids": [Command.create(line) for line in lines],
                **vals,
            }
        )

    def _balanced_entry(self, amount=100.0, count=1, **vals):
        return self._entry(
            [
                {"account_id": self.expense.id, "balance": amount, "name": f"d{i}"}
                for i in range(count)
            ]
            + [
                {
                    "account_id": self.revenue.id,
                    "balance": -amount * count,
                    "name": "c",
                }
            ],
            **vals,
        )

    def test_zero_amount_lines_of_a_posted_invoice_cannot_be_deleted(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2024-01-15",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product_a.id,
                            "price_unit": 100.0,
                            "tax_ids": [Command.set(self.tax_sale_a.ids)],
                        }
                    ),
                    Command.create(
                        {
                            "product_id": self.product_b.id,
                            "quantity": 5,
                            "price_unit": 0.0,
                            "tax_ids": [Command.set(self.tax_sale_a.ids)],
                        }
                    ),
                    Command.create({"display_type": "line_note", "name": "Terms"}),
                ],
            }
        )
        invoice.action_post()
        free_line = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "product" and not line.balance
        )
        note_line = invoice.invoice_line_ids.filtered(
            lambda line: line.display_type == "line_note"
        )
        for line in free_line | note_line:
            with self.assertRaises(UserError):
                line.unlink()
        self.assertEqual(len(invoice.invoice_line_ids), 3)

    def test_new_amount_rebuilds_a_transaction_holding_a_zero_line(self):
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.company_data["default_journal_bank"].id,
                "date": "2024-01-15",
                "payment_ref": "zero line",
                "amount": 100.0,
            }
        )
        st_line.move_id.with_context(skip_readonly_check=True).write(
            {
                "line_ids": [
                    Command.create(
                        {"account_id": self.expense.id, "balance": 0.0, "name": "z"}
                    )
                ]
            }
        )
        self.assertEqual(st_line.move_id.state, "posted")
        st_line.amount = 150.0
        self.assertEqual(
            sorted(st_line.move_id.line_ids.mapped("balance")), [-150.0, 150.0]
        )

    def test_unlink_or_reverse_reverses_an_entry_behind_the_tax_lock_date(self):
        tax_date = fields.Date.today() - timedelta(days=40)
        move = self._entry(
            [
                {
                    "account_id": self.revenue.id,
                    "balance": -100.0,
                    "name": "base",
                    "tax_ids": [Command.set(self.tax_sale_a.ids)],
                },
                {"account_id": self.receivable.id, "balance": 115.0, "name": "rec"},
            ],
            date=tax_date,
        )
        move.action_post()
        self.env.company.account_config_id.tax_lock_date = (
            fields.Date.today() - timedelta(days=10)
        )
        reversal = move._unlink_or_reverse()
        self.assertEqual(move.state, "posted")
        self.assertEqual(reversal.reversed_entry_id, move)

    def test_unlink_or_reverse_reverses_a_reviewed_entry_its_user_cannot_review(self):
        move = self._balanced_entry()
        move.action_post()
        move.checked = True
        with patch.object(
            type(self.env["account.move"]), "_is_user_able_to_review", lambda s: False
        ):
            reversal = move._unlink_or_reverse()
        self.assertEqual(move.state, "posted")
        self.assertEqual(reversal.reversed_entry_id, move)

    def test_unlink_or_reverse_reverses_an_entry_needing_a_cancel_request(self):
        move = self._balanced_entry()
        move.action_post()
        with patch.object(
            type(self.env["account.move"]),
            "_is_cancel_request_required",
            lambda s: s.state == "posted",
        ):
            move.invalidate_recordset(["need_cancel_request"])
            reversal = move._unlink_or_reverse()
        self.assertEqual(move.state, "posted")
        self.assertEqual(reversal.reversed_entry_id, move)

    def test_posting_without_invoice_date_takes_the_rate_of_the_posting_day(self):
        currency = self.setup_other_currency("EUR", rates=[])
        currency.rate_ids.unlink()
        today = fields.Date.today()
        self.env["res.currency.rate"].create(
            [
                {
                    "currency_id": currency.id,
                    "name": today - timedelta(days=days),
                    "rate": rate,
                    "company_id": self.env.company.id,
                }
                for days, rate in ((10, 1.10), (5, 1.50), (0, 2.00))
            ]
        )
        with freeze_time(today - timedelta(days=10)):
            invoice = self.env["account.move"].create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_line_ids": [
                        Command.create({"product_id": self.product_a.id})
                    ],
                }
            )
        with freeze_time(today - timedelta(days=5)):
            invoice.currency_id = currency
            self.assertAlmostEqual(invoice.invoice_currency_rate, 1.5)
        invoice.action_post()
        self.assertEqual(invoice.invoice_date, today)
        self.assertAlmostEqual(invoice.invoice_currency_rate, 2.0)

    def test_a_rate_typed_by_hand_is_flagged_and_survives_the_post(self):
        currency = self.setup_other_currency("EUR")
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "currency_id": currency.id,
                "invoice_line_ids": [Command.create({"product_id": self.product_a.id})],
            }
        )
        self.assertFalse(invoice.invoice_currency_rate_manual)
        invoice.invoice_currency_rate = 7.0
        self.assertTrue(invoice.invoice_currency_rate_manual)
        invoice.action_post()
        self.assertEqual(invoice.invoice_currency_rate, 7.0)
        draft = invoice.copy()
        self.assertFalse(draft.invoice_currency_rate_manual)
        draft.invoice_currency_rate = 7.0
        draft.refresh_invoice_currency_rate()
        self.assertFalse(draft.invoice_currency_rate_manual)

    def _autopost_failing_bill(self):
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "invoice_date": fields.Date.today(),
                "auto_post": "at_date",
                "invoice_line_ids": [
                    Command.create({"product_id": self.product_a.id, "price_unit": 10})
                ],
            }
        )

    def test_autopost_cron_does_not_reselect_a_failed_move(self):
        bill = self._autopost_failing_bill()
        before = bill.message_ids
        Cron = type(self.env["ir.cron"])
        with (
            patch.object(Cron, "_commit_progress", lambda *a, **kw: float("inf")),
            patch.object(self.env.cr, "rollback", lambda: None),
        ):
            for _run in range(3):
                self.env["account.move"]._autopost_draft_entries()
        self.assertEqual(bill.state, "draft")
        self.assertTrue(bill.auto_post_failed)
        self.assertEqual(len(bill.message_ids - before), 1)

        bill.partner_id = self.partner_a
        self.assertFalse(bill.auto_post_failed)
        with patch.object(
            type(self.env["ir.cron"]), "_commit_progress", lambda *a, **kw: 0.0
        ):
            self.env["account.move"]._autopost_draft_entries()
        self.assertEqual(bill.state, "posted")

    def test_autopost_cron_commits_progress_before_locking(self):
        self.init_invoice(
            "out_invoice", amounts=[10.0], invoice_date=fields.Date.today()
        ).auto_post = "at_date"
        events = []
        Cron = type(self.env["ir.cron"])
        Move = type(self.env["account.move"])
        original_lock = Move.try_lock_for_update

        def lock(records, *args, **kwargs):
            events.append("lock")
            return original_lock(records, *args, **kwargs)

        def commit(*args, **kwargs):
            events.append("commit")
            return float("inf")

        def post(records, soft=True):
            events.append("post")

        with (
            patch.object(Cron, "_commit_progress", commit),
            patch.object(Move, "try_lock_for_update", lock),
            patch.object(Move, "_post", post),
        ):
            self.env["account.move"]._autopost_draft_entries()
        self.assertEqual(events, ["commit", "lock", "post", "commit"])

    def test_reversing_a_misc_entry_without_cancel_keeps_its_partner(self):
        move = self._balanced_entry(partner_id=self.partner_a.id)
        move.action_post()
        reversal = move._reverse_moves(cancel=False)
        self.assertEqual(reversal.partner_id, self.partner_a)
        self.assertFalse(move.copy().partner_id)

    def test_receipt_built_from_raw_lines(self):
        receipt = self.env["account.move"].create(
            {
                "move_type": "out_receipt",
                "partner_id": self.partner_a.id,
                "invoice_date": "2024-01-15",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.revenue.id,
                            "price_unit": 100,
                            "quantity": 1,
                            "name": "x",
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.receivable.id,
                            "balance": 100,
                            "name": "y",
                            "date_maturity": "2024-02-01",
                        }
                    ),
                ],
            }
        )
        self.assertEqual(
            receipt.line_ids.filtered(
                lambda line: line.account_id == self.receivable
            ).display_type,
            "payment_term",
        )

    def test_writing_an_archived_account_honours_the_deprecation_bypasses(self):
        archived = self.expense.copy({"code": "699999"})
        archived.active = False
        skip = {"skip_account_deprecation_check": True}
        move = (
            self.env["account.move"]
            .with_context(**skip)
            .create(
                {
                    "move_type": "entry",
                    "journal_id": self.misc_journal.id,
                    "date": "2024-01-15",
                    "line_ids": [
                        Command.create(
                            {"account_id": archived.id, "balance": 100.0, "name": "a"}
                        ),
                        Command.create(
                            {
                                "account_id": self.revenue.id,
                                "balance": -100.0,
                                "name": "b",
                            }
                        ),
                    ],
                }
            )
        )
        revenue_line = move.line_ids.filtered(
            lambda line: line.account_id == self.revenue
        )
        revenue_line.with_context(**skip).write({"account_id": archived.id})
        self.assertEqual(revenue_line.account_id, archived)

        archived_line = move.line_ids[0]
        archived_line.is_imported = True
        archived_line.write({"account_id": archived.id, "name": "z"})
        self.assertEqual(archived_line.name, "z")

        plain_line = self._balanced_entry().line_ids[0]
        with self.assertRaisesRegex(UserError, "archived"):
            plain_line.write({"account_id": archived.id})

    def test_deleting_a_bill_mid_chain_leaves_its_neighbours_unmodified(self):
        bills = self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": f"2024-05-0{day}",
                    "invoice_line_ids": [
                        Command.create({"name": "a", "price_unit": 10, "quantity": 1})
                    ],
                }
                for day in (1, 2, 3)
            ]
        )
        bills.action_post()
        bills.is_manually_modified = False
        middle = bills[1]
        middle.action_draft()
        middle.with_context(force_delete=True).unlink()
        self.assertFalse(bills[2].is_manually_modified)
        self.assertTrue(bills[2].made_sequence_gap)
        self.assertFalse(bills[0].is_manually_modified)

    def test_one_write_of_account_and_distribution_builds_analytic_lines_once(self):
        plan = self.env["account.analytic.plan"].create({"name": "Lifecycle"})
        first, second = self.env["account.analytic.account"].create(
            [{"name": name, "plan_id": plan.id} for name in ("A1", "A2")]
        )
        move = self._entry(
            [
                {
                    "account_id": self.expense.id,
                    "balance": 100.0,
                    "name": "a",
                    "analytic_distribution": {str(first.id): 100},
                },
                {"account_id": self.revenue.id, "balance": -100.0, "name": "b"},
            ]
        )
        move.action_post()
        line = move.line_ids.filtered(lambda l: l.balance > 0)
        other_expense = self.expense.copy({"code": "611111"})
        created = []
        AnalyticLine = type(self.env["account.analytic.line"])
        original_create = AnalyticLine.create

        def spy(records, vals_list):
            result = original_create(records, vals_list)
            created.append(result)
            return result

        with patch.object(AnalyticLine, "create", spy):
            line.write(
                {
                    "account_id": other_expense.id,
                    "analytic_distribution": {str(second.id): 100},
                }
            )
        self.assertEqual(len(created), 1)
        self.assertRecordValues(
            line.analytic_line_ids,
            [{"general_account_id": other_expense.id, "amount": -100.0}],
        )
        self.assertEqual(
            line.analytic_line_ids[plan._column_name()], second, "new distribution"
        )

    def test_resequence_refuses_two_partners_of_a_self_billing_journal(self):
        journal = self.env["account.journal"].create(
            {
                "name": "Self billing",
                "code": "SB",
                "type": "purchase",
                "is_self_billing": True,
            }
        )
        bills = self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": partner.id,
                    "journal_id": journal.id,
                    "invoice_date": "2024-05-01",
                    "invoice_line_ids": [
                        Command.create({"name": "a", "price_unit": 10, "quantity": 1})
                    ],
                }
                for partner in (self.partner_a, self.partner_b)
            ]
        )
        bills.action_post()
        Wizard = self.env["wizard.account.move.resequence"]
        with self.assertRaisesRegex(UserError, "single partner"):
            Wizard.with_context(
                active_model="account.move", active_ids=bills.ids
            ).create({"ordering": "keep"})
        wizard = Wizard.with_context(
            active_model="account.move", active_ids=bills[0].ids
        ).create({"ordering": "keep"})
        wizard.move_ids = bills
        with self.assertRaisesRegex(UserError, "single partner"):
            wizard.resequence()

    def test_reversal_wizard_refuses_a_draft_move_at_run_time(self):
        move = self._balanced_entry()
        wizard = self.env["wizard.account.move.reverse"].create(
            {"move_ids": move.ids, "journal_id": move.journal_id.id}
        )
        with self.assertRaisesRegex(UserError, "posted first"):
            wizard.refund_moves()
        self.assertFalse(move.reversal_move_ids)

    def test_reversal_wizard_of_the_parent_company_reverses_a_branch_entry(self):
        branch = self.env["res.company"].create(
            {"name": "Lifecycle branch", "parent_id": self.env.company.id}
        )
        self.env.user.company_ids |= branch
        move = (
            self.env["account.move"]
            .with_company(branch)
            .create(
                {
                    "move_type": "entry",
                    "journal_id": self.misc_journal.id,
                    "date": "2024-01-15",
                    "line_ids": [
                        Command.create({"account_id": account.id, "balance": balance})
                        for account, balance in (
                            (self.expense, 100.0),
                            (self.revenue, -100.0),
                        )
                    ],
                }
            )
        )
        move.action_post()
        self.assertEqual(move.company_id, branch)
        self.assertEqual(move.journal_id.company_id, self.env.company)
        wizard = self.env["wizard.account.move.reverse"].create(
            {"move_ids": move.ids, "journal_id": move.journal_id.id}
        )
        self.assertEqual(wizard.company_id, self.env.company)
        wizard.refund_moves()
        self.assertTrue(move.reversal_move_ids)

    def test_storno_credit_side_finds_its_reconciled_counterpart(self):
        self.env.company.account_config_id.account_storno = True
        move = self._entry(
            [
                {"account_id": self.receivable.id, "balance": 100.0, "name": "r"},
                {"account_id": self.revenue.id, "balance": -100.0, "name": "i"},
            ],
            partner_id=self.partner_a.id,
        )
        move.action_post()
        reversal = move._reverse_moves(cancel=True)
        original_line = move.line_ids.filtered(
            lambda line: line.account_id == self.receivable
        )
        storno_line = reversal.line_ids.filtered(
            lambda line: line.account_id == self.receivable
        )
        self.assertTrue(storno_line.reconciled)
        self.assertLess(storno_line.debit, 0)
        self.assertIn(original_line.id, storno_line._reconciled_lines())
        self.assertTrue(reversal.has_reconciled_entries)
