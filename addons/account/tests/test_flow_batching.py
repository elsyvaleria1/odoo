import contextlib
import re

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
