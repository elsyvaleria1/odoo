import contextlib
import re
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestFlowBatching(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax = cls.company_data["default_tax_sale"]
        cls.partners = cls.env["res.partner"].create(
            [{"name": f"Batch partner {index}"} for index in range(6)]
        )
        plan = cls.env["account.analytic.plan"].create({"name": "Batch plan"})
        cls.analytic_accounts = cls.env["account.analytic.account"].create(
            [
                {"name": f"Batch analytic {index}", "plan_id": plan.id}
                for index in range(6)
            ]
        )
        cls.invoices = cls.env["account.move"].concat(
            *(
                cls.init_invoice(
                    "out_invoice",
                    partner=partner,
                    invoice_date="2026-01-15",
                    amounts=[100.0],
                    taxes=cls.tax,
                )
                for partner in cls.partners
            )
        )
        for invoice, analytic in zip(cls.invoices, cls.analytic_accounts, strict=True):
            invoice.invoice_line_ids.analytic_distribution = {str(analytic.id): 100}

    def _count_matching(self, pattern, run) -> int:
        with self.capturedQueries() as queries:
            run()
        return sum(1 for query in queries if re.search(pattern, query))

    def test_analytic_lines_check_their_accounts_once_per_batch(self):
        def create_analytic_lines(size):
            lines = self.env["account.move"].browse(self.invoices[:size].ids)
            lines.invoice_line_ids._create_analytic_lines()

        self.assertQueriesConstant(create_analytic_lines, small=2, large=6)

    def test_an_analytic_account_deleted_since_is_left_out(self):
        line = self.invoices[0].invoice_line_ids
        kept, dropped = self.analytic_accounts[:2]
        line.analytic_distribution = {f"{kept.id},{dropped.id}": 100}
        dropped.unlink()

        line._create_analytic_lines()

        self.assertEqual(line.analytic_line_ids[kept.plan_id._column_name()], kept)

    def test_registering_payments_links_entries_and_invoices_once(self):
        self.invoices.action_post()

        def register(invoices):
            self.env["wizard.account.move.line.pay"].with_context(
                active_model="account.move", active_ids=invoices.ids
            ).create(
                {"group_payment": False, "payment_date": "2026-01-20"}
            ).action_create_payments()

        def lookups(invoices):
            with (
                contextlib.closing(self.cr.savepoint(flush=True)),
                self.capturedQueries() as queries,
            ):
                register(invoices)
            return {
                pattern: sum(1 for query in queries if re.search(pattern, query))
                for pattern in (
                    r'"account_move_line"\."payment_id" IN',
                    r'"account_return_payment"\."payment_id" IN',
                    r'"account_move__matched_payment_ids"',
                    r"ARRAY_AGG\(DISTINCT invoice\.id\)",
                    r"ARRAY_AGG\(DISTINCT counterpart_move\.statement_line_id\)",
                    r"ARRAY_AGG\(DISTINCT payment_id\)",
                    r'INSERT INTO "account_move__account_payment"',
                )
            }

        register(self.invoices[5:])
        self.assertEqual(lookups(self.invoices[:2]), lookups(self.invoices[:5]))
        register(self.invoices[:5])
        self.assertEqual(
            set(self.invoices[:5].mapped("payment_state")),
            {self.env["account.move"]._get_invoice_in_payment_state()},
        )
        self.assertEqual(
            [len(invoice.matched_payment_ids) for invoice in self.invoices[:5]],
            [1] * 5,
        )
        self.assertEqual(
            set(self.invoices[:5].matched_payment_ids.move_id.mapped("state")),
            {"posted"},
        )

    def test_entries_created_with_their_payments_stay_draft(self):
        payments = self.env["account.payment"].create(
            [
                {
                    "amount": 10.0 * (index + 1),
                    "partner_id": partner.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "journal_id": self.company_data["default_journal_bank"].id,
                    "write_off_line_vals": [],
                }
                for index, partner in enumerate(self.partners[:3])
            ]
        )

        self.assertEqual(payments.mapped("state"), ["in_process"] * 3)
        self.assertEqual(payments.move_id.mapped("state"), ["draft"] * 3)
        self.assertEqual(
            [payment.move_id.origin_payment_id for payment in payments],
            list(payments),
        )
        self.assertEqual(
            [payment.move_id.line_ids.payment_id for payment in payments],
            list(payments),
        )

        payments.action_post()

        self.assertEqual(payments.move_id.mapped("state"), ["posted"] * 3)

    def test_matched_invoices_are_linked_in_one_write(self):
        self.invoices[:3].action_post()
        payments = self.env["account.payment"].create(
            [
                {
                    "amount": 10.0,
                    "partner_id": invoice.partner_id.id,
                    "partner_type": "customer",
                    "payment_type": "inbound",
                    "journal_id": self.company_data["default_journal_bank"].id,
                }
                for invoice in self.invoices[:3]
            ]
        )
        links = [
            self.invoices[0],
            self.invoices[1] | self.invoices[2],
            self.invoices[2],
        ]

        inserts = self._count_matching(
            r'INSERT INTO "account_move__account_payment"',
            lambda: payments._link_matched_invoices(links),
        )

        self.assertEqual(inserts, 1)
        self.assertEqual(self.invoices[0].matched_payment_ids, payments[0])
        self.assertEqual(self.invoices[1].matched_payment_ids, payments[1])
        self.assertEqual(self.invoices[2].matched_payment_ids, payments[1:])
        self.assertEqual(payments[1].invoice_ids, self.invoices[1] | self.invoices[2])

    def _move_writes(self, fname, run) -> list:
        Move = type(self.env["account.move"])
        original = Move.write
        writes = []

        def counted(records, vals):
            if fname in vals:
                writes.append(records.ids)
            return original(records, vals)

        with patch.object(Move, "write", counted):
            run()
        return writes

    def test_settling_the_tax_country_writes_only_the_moves_it_moves(self):
        self.invoices.action_post()
        foreign = self.env["res.country"].search(
            [("id", "!=", self.invoices[0].tax_country_id.id)], limit=1
        )
        stale = self.invoices[:2]
        stale.with_context(skip_is_manually_modified=True).write(
            {"tax_country_id": foreign.id}
        )

        writes = self._move_writes(
            "tax_country_id", self.invoices._update_tax_country_id
        )

        self.assertEqual(writes, [stale.ids])
        self.assertEqual(self.invoices.tax_country_id, self.invoices[2].tax_country_id)

    def test_entries_created_with_payments_resolve_fiscal_positions_together(self):
        Move = type(self.env["account.move"])
        original = Move._compute_fiscal_position_id
        batches = []

        def counted(moves):
            batches.append(len(moves))
            return original(moves)

        with patch.object(Move, "_compute_fiscal_position_id", counted):
            self.env["account.payment"].create(
                [
                    {
                        "amount": 10.0,
                        "partner_id": partner.id,
                        "partner_type": "customer",
                        "payment_type": "inbound",
                        "journal_id": self.company_data["default_journal_bank"].id,
                        "write_off_line_vals": [],
                    }
                    for partner in self.partners
                ]
            )

        self.assertEqual(batches, [len(self.partners)])

    def test_fiscal_positions_of_a_batch_are_resolved_together(self):
        field = self.env["account.move"]._fields["fiscal_position_id"]

        def compute(size):
            moves = self.env["account.move"].browse(self.invoices[:size].ids)
            self.env.add_to_compute(field, moves)
            moves.mapped("fiscal_position_id")

        self.assertQueriesConstant(compute, small=2, large=6)

    def test_deleting_entries_reads_no_lines_per_entry(self):
        entries = self.env["account.move"].create(
            [
                {
                    "move_type": "entry",
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.company_data[
                                    "default_account_revenue"
                                ].id,
                                "balance": sign * 10.0,
                            }
                        )
                        for sign in (1, -1)
                    ],
                }
                for _index in range(6)
            ]
        )

        def delete(size):
            self.env["account.move"].browse(entries[:size].ids).unlink()

        self.assertQueriesConstant(delete, small=2, large=6)
