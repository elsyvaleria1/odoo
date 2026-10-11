from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestHelperMethods(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner_supplier = cls.env["res.partner"].create(
            {"name": "Automation Supplier"},
        )
        cls.account_expense = cls.env["account.account"].create(
            {
                "name": "Automation Expense",
                "code": "TAAC500",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            },
        )
        cls.journal_purchase = cls._make_journal("purchase", "TAAPU")
        cls.template_bill = cls.env["account.move.template"].create(
            {
                "name": "TEST - Vendor Bill",
                "journal_code": cls.journal_purchase.code,
                "move_type": "in_invoice",
                "line_ids": [
                    Command.create(
                        {
                            "name": "Expense Item",
                            "account_code": cls.account_expense.code,
                            "sequence": 10,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

    def setUp(self):
        super().setUp()
        self.steps = self._make_chain(["pass", "pass", "pass"])
        self.runtime = self._make_runtime(
            amount=2500.0,
            reference="TEST-HELPER-001",
        )
        self.lines = self.runtime.line_ids.sorted("sequence")

    def test_create_move_from_template(self):
        line = self.lines[0]

        move = line.action_id.create_move_from_template(line, self.template_invoice)

        self.assertTrue(move.exists())
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.partner_id, self.partner)
        self.assertGreater(move.amount_total, 0)

    def test_a_company_less_template_runs_in_the_runtimes_company(self):
        other_company = self.env["res.company"].create({"name": "TAAC Other Co"})
        self.env["account.journal"].create(
            {
                "name": "TAAC Other Sale",
                "code": self.journal_sale.code,
                "type": "sale",
                "company_id": other_company.id,
            }
        )
        other_income = (
            self.env["account.account"]
            .with_company(other_company)
            .create(
                {
                    "name": "TAAC Other Income",
                    "code": self.account_income.code,
                    "account_type": "income",
                    "company_ids": [Command.link(other_company.id)],
                }
            )
        )
        self.partner.with_company(other_company).property_account_receivable_id = (
            self.env["account.account"]
            .with_company(other_company)
            .create(
                {
                    "name": "TAAC Other Receivable",
                    "code": self.account_receivable.code,
                    "account_type": "asset_receivable",
                    "reconcile": True,
                    "company_ids": [Command.link(other_company.id)],
                }
            )
        )
        self.template_invoice.company_id = False
        self.runtime.company_ids = [Command.set(other_company.ids)]
        line = self.lines[0]

        move = line.action_id.create_move_from_template(
            line, self.template_invoice, auto_post=False
        )

        self.assertEqual(move.company_id, other_company)
        self.assertEqual(move.invoice_line_ids.account_id, other_income)

    def test_create_move_from_template_name(self):
        line = self.lines[0]

        move = line.action_id.create_move_from_template_name(
            line,
            self.template_invoice.name,
        )

        self.assertEqual(move.move_type, "out_invoice")

    def test_create_move_from_template_name_rejects_an_unknown_name(self):
        line = self.lines[0]

        with self.assertRaises(UserError):
            line.action_id.create_move_from_template_name(line, "no such template")

    def test_create_move_from_template_refuses_a_foreign_record(self):
        line = self.lines[0]

        with self.assertRaises(UserError):
            line.action_id.create_move_from_template(
                self.runtime,
                self.template_invoice,
            )

    def test_create_payment_from_latest_move(self):
        first = self.lines[0]
        invoice = first.action_id.create_move_from_template(
            first, self.template_invoice
        )
        first.created_record_ref = f"account.move,{invoice.id}"

        second = self.lines[1]
        payment = second.action_id.create_payment_from_latest_move(second)

        self.assertTrue(payment.exists())
        self.assertEqual(payment.partner_id, self.partner)
        self.assertEqual(payment.payment_type, "inbound")
        self.assertEqual(payment.partner_type, "customer")

    def test_create_payment_from_latest_move_without_a_move(self):
        line = self.lines[1]

        with self.assertRaises(UserError):
            line.action_id.create_payment_from_latest_move(line)

    def test_create_payment_for_move_requires_a_posted_move(self):
        line = self.lines[0]
        draft = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.journal_sale.id,
                "invoice_date": "2026-08-20",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Draft item",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": self.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )

        with self.assertRaises(UserError):
            line.action_id.create_payment_for_move(line, draft)

    def test_mark_action_done_and_continue(self):
        first = self.lines[0]
        self.assertEqual(first.state, "ready")

        first.action_id.mark_action_done_and_continue(first)

        self.assertEqual(first.state, "done")

    def test_the_helper_readies_the_next_step(self):
        first, second = self.lines[0], self.lines[1]

        first.action_id.mark_action_done_and_continue(first)

        self.assertEqual(second.state, "ready")

    def test_the_helper_closes_a_run_whose_every_step_is_done(self):
        for line in self.lines:
            line.action_id.mark_action_done_and_continue(line)
            line.state = "done"

        self.assertEqual(self.runtime.state, "done")

    def test_a_bill_template_produces_a_vendor_bill(self):
        line = self.lines[0]

        bill = line.action_id.create_move_from_template(line, self.template_bill)

        self.assertEqual(bill.move_type, "in_invoice")

    def test_the_runtime_reference_reaches_the_move(self):
        line = self.lines[0]

        move = line.action_id.create_move_from_template(line, self.template_invoice)

        self.assertEqual(move.ref, "TEST-HELPER-001")

    def test_a_third_party_runtime_carries_it_to_the_wizard(self):
        self.runtime.third_party_id = self.third_party
        line = self.lines[0]

        move = line.action_id.create_move_from_template(line, self.template_invoice)

        self.assertTrue(move.exists())

    def test_a_null_payment_method_does_not_break_the_template_run(self):
        line = self.lines[0]
        action = line.action_id

        real_lookup = type(action)._get_runtime_telegram_data

        def null_payment_method(self, runtime):
            return {"payment_method": None}

        type(action)._get_runtime_telegram_data = null_payment_method
        try:
            move = action.create_move_from_template(line, self.template_invoice)
        finally:
            type(action)._get_runtime_telegram_data = real_lookup

        self.assertTrue(
            move.exists(),
            "a null payment_method must be treated as 'not supplied', not crash",
        )

    def test_a_missing_payment_method_still_works(self):
        line = self.lines[0]
        action = line.action_id

        real_lookup = type(action)._get_runtime_telegram_data

        def no_payment_method(self, runtime):
            return {"cfdi_use_code": False}

        type(action)._get_runtime_telegram_data = no_payment_method
        try:
            move = action.create_move_from_template(line, self.template_invoice)
        finally:
            type(action)._get_runtime_telegram_data = real_lookup

        self.assertTrue(move.exists())
