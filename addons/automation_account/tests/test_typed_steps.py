from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import freeze_time
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .common import AutomationAccountCommon

LINE_LOGGER = "odoo.addons.automation.models.automation_runtime_line"


class TypedStepCase(AutomationAccountCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.template_refund = cls.env["account.move.template"].create(
            {
                "name": "TEST - Customer Credit Note",
                "journal_code": cls.journal_sale.code,
                "move_type": "out_refund",
                "invoice_payment_term_id": cls.immediate.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Credit Item",
                            "account_code": cls.account_income.code,
                            "sequence": 10,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

    def _typed_step(self, state, name="Step", predecessors=None, **vals):
        step = self.env["ir.actions.server"].create(
            {
                "name": name,
                "automation_rule_id": self.automation.id,
                "model_id": self.model_line.id,
                "usage": "automation",
                "state": state,
                "sequence": 10 + len(self.automation.action_server_ids),
                **vals,
            },
        )
        self._link_steps(predecessors, step)
        return step

    def _document_step(self, template=None, **vals):
        return self._typed_step(
            "workflow_create_document",
            workflow_template_id=(template or self.template_invoice).id,
            **vals,
        )

    def _statement_line(self, amount=100.0):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "date": "2026-08-21",
                "payment_ref": "Typed step statement line",
                "partner_id": self.partner.id,
                "amount": amount,
            },
        )

    def _line(self, runtime, step):
        return runtime.line_ids.filtered(lambda line: line.action_id == step)


@tagged("post_install", "-at_install")
class TestDocumentStep(TypedStepCase):
    def test_a_document_step_creates_and_posts_what_its_template_describes(self):
        step = self._document_step()
        runtime = self._make_runtime()

        runtime.action_next_step()

        line = self._line(runtime, step)
        move = line.created_record_ref
        self.assertEqual(line.state, "done")
        self.assertEqual(move._name, "account.move")
        self.assertEqual(move.move_type, "out_invoice")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.partner_id, self.partner)
        self.assertEqual(move.amount_untaxed, 100.0)
        self.assertEqual(runtime.state, "done")

    def test_a_document_step_can_leave_a_draft_to_review(self):
        step = self._document_step(workflow_auto_post=False)
        runtime = self._make_runtime()

        runtime.action_next_step()

        self.assertEqual(self._line(runtime, step).created_record_ref.state, "draft")

    def test_the_step_says_who_the_document_is_issued_to(self):
        to_partner = self._document_step(name="To partner")
        to_other = self._document_step(
            name="To alternative",
            predecessors=to_partner,
            workflow_partner_source="third_party",
        )
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        runtime.action_run_all()

        self.assertEqual(
            self._line(runtime, to_partner).created_record_ref.partner_id,
            self.partner,
        )
        self.assertEqual(
            self._line(runtime, to_other).created_record_ref.partner_id,
            self.third_party,
        )

    def test_the_step_outranks_the_template_on_who_is_invoiced(self):
        self.template_invoice.use_third_party = True
        step = self._document_step(workflow_partner_source="partner")
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        runtime.action_next_step()

        self.assertEqual(
            self._line(runtime, step).created_record_ref.partner_id,
            self.partner,
        )

    def test_a_run_without_an_alternative_partner_issues_to_its_partner(self):
        step = self._document_step(workflow_partner_source="third_party")
        runtime = self._make_runtime()

        runtime.action_next_step()

        self.assertEqual(
            self._line(runtime, step).created_record_ref.partner_id,
            self.partner,
        )

    def test_picking_a_template_takes_its_partner_choice(self):
        self.template_refund.write({"use_third_party": True, "company_id": False})
        step = self.env["ir.actions.server"].new(
            {"state": "workflow_create_document"},
        )

        step.workflow_template_id = self.template_refund
        step._onchange_workflow_template_id()

        self.assertEqual(step.workflow_partner_source, "third_party")
        self.assertEqual(step.workflow_company_source, "transaction")

        self.template_refund.company_id = self.company
        step._onchange_workflow_template_id()

        self.assertEqual(step.workflow_company_source, "template")

    def test_a_document_step_can_be_dated_the_day_it_runs(self):
        step = self._document_step(workflow_date_source="today")
        runtime = self._make_runtime(date="2026-08-01")

        with freeze_time("2026-08-27"):
            runtime.action_next_step()

        move = self._line(runtime, step).created_record_ref
        self.assertEqual(str(move.invoice_date), "2026-08-27")

    def test_a_document_step_can_be_dated_the_day_the_money_came_in(self):
        st_line = self._statement_line()
        on_run_date = self._document_step(name="On the run's date")
        on_payment_date = self._document_step(
            self.template_refund,
            name="On the bank line's date",
            predecessors=on_run_date,
            workflow_date_source="statement",
        )
        runtime = self._make_runtime(st_line_id=st_line.id, date="2026-08-31")

        runtime.action_run_all()

        self.assertEqual(
            str(self._line(runtime, on_run_date).created_record_ref.invoice_date),
            "2026-08-31",
        )
        self.assertEqual(
            self._line(runtime, on_payment_date).created_record_ref.invoice_date,
            st_line.date,
        )

    def test_a_run_without_a_bank_line_dates_such_a_step_with_its_own_date(self):
        step = self._document_step(workflow_date_source="statement")
        runtime = self._make_runtime(date="2026-08-31")

        runtime.action_next_step()

        move = self._line(runtime, step).created_record_ref
        self.assertEqual(str(move.invoice_date), "2026-08-31")

    def test_a_document_step_replaces_the_taxes_it_is_given(self):
        tax = self.env["account.tax"].create(
            {
                "name": "TAA Zero",
                "amount": 0.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
            },
        )
        step = self._document_step(workflow_tax_ids=[Command.set(tax.ids)])
        runtime = self._make_runtime()

        runtime.action_next_step()

        move = self._line(runtime, step).created_record_ref
        self.assertEqual(move.invoice_line_ids.tax_ids, tax)
        self.assertEqual(move.state, "posted")

    def test_a_document_step_without_a_template_is_refused(self):
        with self.assertRaises(ValidationError):
            self._typed_step("workflow_create_document")

    def test_a_typed_step_does_not_run_outside_a_workflow_run(self):
        step = self._document_step()

        with self.assertRaises(UserError):
            step.run()

    def test_typed_steps_are_only_offered_to_workflow_steps(self):
        step = self._document_step()
        elsewhere = self.env["ir.actions.server"].new(
            {"model_id": self.env["ir.model"]._get("res.partner").id},
        )

        self.assertIn("workflow_create_document", step.allowed_states)
        self.assertNotIn("workflow_create_document", elsewhere.allowed_states)
        self.assertNotIn("workflow_reconcile_statement", elsewhere.allowed_states)


@tagged("post_install", "-at_install")
class TestDocumentStepCompany(TypedStepCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.other_company = cls.env["res.company"].create(
            {
                "name": "TAA Other Company",
                "country_id": cls.company.account_fiscal_country_id.id,
            },
        )
        cls.env.user.company_ids |= cls.other_company
        other = cls.env["account.account"].with_company(cls.other_company)
        cls.other_receivable = other.create(
            {
                "name": "Automation Receivable",
                "code": cls.account_receivable.code,
                "account_type": "asset_receivable",
                "reconcile": True,
                "company_ids": [Command.set(cls.other_company.ids)],
            },
        )
        cls.other_income = other.create(
            {
                "name": "Automation Income",
                "code": cls.account_income.code,
                "account_type": "income",
                "company_ids": [Command.set(cls.other_company.ids)],
            },
        )
        cls.other_journal = cls.env["account.journal"].create(
            {
                "name": "Automation sale, other company",
                "code": cls.journal_sale.code,
                "type": "sale",
                "company_id": cls.other_company.id,
                "default_account_id": cls.other_income.id,
            },
        )
        partners = (cls.partner | cls.third_party).with_company(cls.other_company)
        partners.property_account_receivable_id = cls.other_receivable

    def _make_vehicle_runtime(self, **vals):
        return self._make_runtime(
            st_line_id=self._statement_line().id,
            company_ids=[Command.set((self.company | self.other_company).ids)],
            **vals,
        )

    def test_the_vehicle_invoices_and_the_other_company_credits_the_partner(self):
        invoice = self._document_step(
            name="Invoice",
            workflow_company_source="statement",
            workflow_partner_source="third_party",
            workflow_auto_post=False,
        )
        refund = self._document_step(
            self.template_refund,
            name="Credit note",
            predecessors=invoice,
            workflow_auto_post=False,
        )
        runtime = self._make_vehicle_runtime(third_party_id=self.third_party.id)

        runtime.action_run_all()

        invoice_move = self._line(runtime, invoice).created_record_ref
        refund_move = self._line(runtime, refund).created_record_ref
        self.assertEqual(runtime.state, "done")
        self.assertEqual(runtime._get_vehicle_company(), self.company)
        self.assertEqual(runtime._get_transaction_company(), self.other_company)
        self.assertEqual(invoice_move.company_id, self.company)
        self.assertEqual(invoice_move.partner_id, self.third_party)
        self.assertEqual(refund_move.company_id, self.other_company)
        self.assertEqual(refund_move.journal_id, self.other_journal)
        self.assertEqual(refund_move.partner_id, self.partner)

    def test_a_run_of_two_companies_is_listed_in_each(self):
        self._document_step(workflow_auto_post=False)
        runtime = self._make_vehicle_runtime()
        readers = {
            company: self.env["res.users"].create(
                {
                    "name": f"Reader of {company.name}",
                    "login": f"taa_reader_{company.id}",
                    "company_id": company.id,
                    "company_ids": [Command.set(company.ids)],
                    "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
                },
            )
            for company in self.company | self.other_company
        }

        for company, reader in readers.items():
            with self.subTest(company=company.name):
                self.assertEqual(
                    self.env["automation.runtime"]
                    .with_user(reader)
                    .search([("id", "=", runtime.id)]),
                    runtime,
                )

    def test_the_warning_looks_into_both_companies_from_either_one(self):
        self._document_step(
            name="Credit note",
            workflow_tax_ids=[Command.set(self._other_tax().ids)],
        )
        runtime = self._make_vehicle_runtime()

        for company in self.company | self.other_company:
            with self.subTest(seen_from=company.name):
                seen = runtime.with_context(allowed_company_ids=company.ids)
                seen.invalidate_recordset(["problem_message"])
                self.assertFalse(seen.problem_message)
                self.assertEqual(seen._get_vehicle_company(), self.company)

    def test_the_start_dialog_previews_both_companies_from_the_bank_line_s(self):
        invoice = self._document_step(
            name="Invoice",
            workflow_company_source="statement",
        )
        self._document_step(
            self.template_refund, name="Credit note", predecessors=invoice
        )
        st_line = self._statement_line()

        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
                allowed_company_ids=self.company.ids,
            )
            .create(
                {
                    "automation_id": self.automation.id,
                    "company_ids": [
                        Command.set((self.company | self.other_company).ids),
                    ],
                },
            )
        )

        self.assertFalse(wizard.problem_message)
        invoice_row, refund_row = str(wizard.plan_preview).split("<li>")[1:3]
        self.assertIn(self.company.name, invoice_row)
        self.assertIn(self.other_company.name, refund_row)

    def _other_tax(self):
        group = self.env["account.tax.group"].create(
            {
                "name": "TAA Group",
                "company_ids": [Command.set(self.other_company.ids)],
            },
        )
        return (
            self.env["account.tax"]
            .with_company(self.other_company)
            .create(
                {
                    "name": "TAA Other Zero",
                    "amount": 0.0,
                    "amount_type": "percent",
                    "type_tax_use": "sale",
                    "company_ids": [Command.set(self.other_company.ids)],
                    "tax_group_id": group.id,
                },
            )
        )

    def test_two_companies_without_a_bank_line_cannot_be_told_apart(self):
        self._document_step(workflow_auto_post=False)

        runtime = self._make_runtime(
            company_ids=[Command.set((self.company | self.other_company).ids)],
        )

        self.assertIn("no bank statement line", runtime.problem_message)

    def test_a_bank_line_of_another_company_is_announced(self):
        self._document_step(workflow_auto_post=False)

        runtime = self._make_runtime(
            st_line_id=self._statement_line().id,
            company_ids=[Command.set(self.other_company.ids)],
        )

        self.assertIn(self.company.name, runtime.problem_message)

    def test_a_template_s_own_company_can_be_the_one_a_step_creates_in(self):
        self.template_invoice.company_id = self.other_company
        step = self._document_step(
            workflow_company_source="template",
            workflow_auto_post=False,
        )
        runtime = self._make_runtime()

        runtime.action_next_step()

        self.assertEqual(
            self._line(runtime, step).created_record_ref.company_id,
            self.other_company,
        )

    def test_a_run_of_one_company_creates_everything_there(self):
        in_vehicle = self._document_step(
            name="In the bank line's",
            workflow_company_source="statement",
            workflow_auto_post=False,
        )
        in_transaction = self._document_step(
            name="In the transaction's",
            predecessors=in_vehicle,
            workflow_auto_post=False,
        )
        runtime = self._make_runtime()

        runtime.action_run_all()

        for step in in_vehicle | in_transaction:
            self.assertEqual(
                self._line(runtime, step).created_record_ref.company_id,
                self.company,
            )

    def test_a_replacement_tax_stands_for_its_namesake_in_the_other_company(self):
        Tax = self.env["account.tax"]
        vals = {"amount": 0.0, "amount_type": "percent", "type_tax_use": "sale"}
        here = Tax.create({"name": "TAA Zero", **vals})
        group = self.env["account.tax.group"].create(
            {
                "name": "TAA Group",
                "company_ids": [Command.set(self.other_company.ids)],
            },
        )
        there = Tax.with_company(self.other_company).create(
            {
                "name": "TAA Zero",
                "company_ids": [Command.set(self.other_company.ids)],
                "tax_group_id": group.id,
                **vals,
            },
        )
        step = self._document_step(
            workflow_tax_ids=[Command.set(here.ids)],
            workflow_auto_post=False,
        )
        runtime = self._make_vehicle_runtime()

        runtime.action_next_step()

        move = self._line(runtime, step).created_record_ref
        self.assertEqual(move.invoice_line_ids.tax_ids, there)

    @mute_logger(LINE_LOGGER)
    def test_a_replacement_tax_the_other_company_lacks_fails_the_step(self):
        here = self.env["account.tax"].create(
            {
                "name": "TAA Only Here",
                "amount": 0.0,
                "amount_type": "percent",
                "type_tax_use": "sale",
            },
        )
        step = self._document_step(workflow_tax_ids=[Command.set(here.ids)])
        runtime = self._make_vehicle_runtime()

        self.assertIn("TAA Only Here", runtime.problem_message)

        runtime.action_next_step()

        self.assertEqual(self._line(runtime, step).state, "error")
        self.assertIn("TAA Only Here", self._line(runtime, step).error_message)
        self.assertFalse(
            self.env["account.move"].search_count(
                [("ref", "=", runtime.reference), ("ref", "!=", False)],
            ),
        )

    def test_the_run_is_told_a_journal_is_missing_where_a_step_creates(self):
        self.other_journal.code = "TAAXX"
        self._document_step(name="Credit note")
        runtime = self._make_vehicle_runtime()

        self.assertIn("Credit note", runtime.problem_message)
        self.assertIn(self.other_company.name, runtime.problem_message)

    def test_settling_across_companies_asks_for_the_owed_company_s_journal(self):
        document = self._document_step(name="Invoice elsewhere")
        self._typed_step(
            "workflow_reconcile_statement",
            name="Reconcile",
            predecessors=document,
        )
        runtime = self._make_vehicle_runtime()

        self.assertIn("Reconcile", runtime.problem_message)
        self.assertIn("Intercompany Collection Journal", runtime.problem_message)

        self.other_company.automation_intercompany_journal_id = self.env[
            "account.journal"
        ].create(
            {
                "name": "TAA Intercompany",
                "code": "TAAIC",
                "type": "general",
                "company_id": self.other_company.id,
            },
        )
        runtime.invalidate_recordset(["problem_message"])

        self.assertFalse(runtime.problem_message)


@tagged("post_install", "-at_install")
class TestStatementSteps(TypedStepCase):
    def test_the_register_step_links_the_statement_line_s_entry(self):
        st_line = self._statement_line()
        step = self._typed_step("workflow_register_statement")
        runtime = self._make_runtime(st_line_id=st_line.id)

        runtime.action_next_step()

        line = self._line(runtime, step)
        self.assertEqual(line.state, "done")
        self.assertEqual(line.created_record_ref, st_line.move_id)

    @mute_logger(LINE_LOGGER)
    def test_the_register_step_fails_without_a_statement_line(self):
        step = self._typed_step("workflow_register_statement", name="Register")
        runtime = self._make_runtime()

        self.assertIn("Register", runtime.problem_message)

        runtime.action_next_step()

        self.assertEqual(self._line(runtime, step).state, "error")
        self.assertEqual(runtime.state, "error")

    def test_the_reconcile_step_reconciles_the_document_before_it(self):
        st_line = self._statement_line()
        register = self._typed_step("workflow_register_statement", name="Register")
        document = self._document_step(name="Invoice", predecessors=register)
        reconcile = self._typed_step(
            "workflow_reconcile_statement",
            name="Reconcile",
            predecessors=document,
        )
        runtime = self._make_runtime(st_line_id=st_line.id)
        runtime.action_next_step()
        runtime.action_next_step()
        move = self._line(runtime, document).created_record_ref

        with patch.object(
            type(st_line),
            "set_line_bank_statement_line",
            autospec=True,
        ) as reconciled:
            runtime.action_next_step()

        self.assertFalse(runtime.problem_message)
        self.assertEqual(self._line(runtime, reconcile).state, "done")
        self.assertEqual(runtime.state, "done")
        receivable = move.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable",
        )
        reconciled.assert_called_once_with(st_line, receivable.ids)

    def test_the_credit_note_step_applies_the_note_before_it(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.journal_sale.id,
                "invoice_date": "2026-08-20",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Open item",
                            "quantity": 1,
                            "price_unit": 250.0,
                            "account_id": self.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        invoice.action_post()
        refund = self._document_step(self.template_refund, name="Credit note")
        apply = self._typed_step(
            "workflow_apply_credit_note",
            name="Apply",
            predecessors=refund,
        )
        runtime = self._make_runtime()

        runtime.action_run_all()

        self.assertEqual(self._line(runtime, apply).state, "done")
        self.assertEqual(runtime.state, "done")
        self.assertEqual(invoice.amount_residual, 150.0)


@tagged("post_install", "-at_install")
class TestChangePartnerStep(TypedStepCase):
    def _refund_then_change(self):
        refund = self._document_step(
            self.template_refund,
            name="Credit note",
            workflow_partner_source="third_party",
        )
        change = self._typed_step(
            "workflow_change_partner",
            name="Change partner",
            predecessors=refund,
        )
        return refund, change

    def test_the_document_before_it_is_issued_to_the_run_s_partner(self):
        refund, change = self._refund_then_change()
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        runtime.action_next_step()
        note = self._line(runtime, refund).created_record_ref
        number = note.name
        self.assertEqual(note.partner_id, self.third_party)
        runtime.action_next_step()

        self.assertEqual(self._line(runtime, change).state, "done")
        self.assertEqual(self._line(runtime, change).created_record_ref, note)
        self.assertEqual(note.partner_id, self.partner)
        self.assertEqual(note.state, "posted")
        self.assertEqual(note.name, number)
        receivable = note.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable",
        )
        self.assertEqual(receivable.partner_id, self.partner)

    def test_a_document_already_applied_is_left_alone(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.third_party.id,
                "journal_id": self.journal_sale.id,
                "invoice_date": "2026-08-20",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Open item",
                            "quantity": 1,
                            "price_unit": 250.0,
                            "account_id": self.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        invoice.action_post()
        refund = self._document_step(
            self.template_refund,
            name="Credit note",
            workflow_partner_source="third_party",
        )
        apply = self._typed_step(
            "workflow_apply_credit_note",
            name="Apply",
            predecessors=refund,
        )
        change = self._typed_step(
            "workflow_change_partner",
            name="Change partner",
            predecessors=apply,
        )
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        with mute_logger(LINE_LOGGER):
            runtime.action_run_all()

        line = self._line(runtime, change)
        self.assertEqual(line.state, "error")
        self.assertIn("already applied", line.error_message)
        note = self._line(runtime, refund).created_record_ref
        self.assertEqual(note.partner_id, self.third_party)
        self.assertEqual(note.state, "posted")

    def test_a_document_already_issued_to_the_partner_is_unchanged(self):
        refund = self._document_step(self.template_refund, name="Credit note")
        change = self._typed_step(
            "workflow_change_partner",
            name="Change partner",
            predecessors=refund,
        )
        runtime = self._make_runtime()

        runtime.action_run_all()

        note = self._line(runtime, refund).created_record_ref
        self.assertEqual(self._line(runtime, change).state, "done")
        self.assertEqual(note.partner_id, self.partner)
        self.assertEqual(note.state, "posted")

    def test_without_an_earlier_document_the_step_fails(self):
        change = self._typed_step("workflow_change_partner", name="Change partner")
        runtime = self._make_runtime()

        with mute_logger(LINE_LOGGER):
            runtime.action_next_step()

        self.assertEqual(self._line(runtime, change).state, "error")

    def test_the_step_says_who_the_document_goes_to(self):
        _refund, change = self._refund_then_change()
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        summary = change._get_workflow_step_summary(runtime)

        self.assertIn(self.partner.display_name, summary)


@tagged("post_install", "-at_install")
class TestStepResults(TypedStepCase):
    def _open_invoice(self, amount):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.journal_sale.id,
                "invoice_date": "2026-08-20",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Open item",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": self.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        invoice.action_post()
        return invoice

    def _refund_then_apply(self):
        refund = self._document_step(self.template_refund, name="Credit note")
        apply = self._typed_step(
            "workflow_apply_credit_note",
            name="Apply",
            predecessors=refund,
        )
        return refund, apply

    def test_the_apply_step_reports_what_it_applied_and_what_is_left(self):
        invoice = self._open_invoice(60.0)
        refund, apply = self._refund_then_apply()
        runtime = self._make_runtime()

        runtime.action_run_all()

        line = self._line(runtime, apply)
        note = self._line(runtime, refund).created_record_ref
        self.assertEqual(
            line.output,
            {
                "credit_note": note.name,
                "applied": 60.0,
                "invoices": [invoice.name],
                "open_credit": 40.0,
            },
        )
        self.assertIn(invoice.name, line.output_summary)
        self.assertEqual(line.created_record_ref, note)

    def test_the_apply_step_says_so_when_it_applies_nothing(self):
        _refund, apply = self._refund_then_apply()
        runtime = self._make_runtime()

        runtime.action_run_all()

        line = self._line(runtime, apply)
        self.assertEqual(line.state, "done")
        self.assertEqual(line.output["applied"], 0.0)
        self.assertEqual(line.output["invoices"], [])
        self.assertEqual(line.output["open_credit"], 100.0)

    def test_a_flow_routes_an_open_credit_to_a_review_step(self):
        self._open_invoice(60.0)
        _refund, apply = self._refund_then_apply()
        review = self._make_step("pass", name="Review the open credit")
        settled = self._make_step("pass", name="Fully applied")
        for target, expression in (
            (review, "output['open_credit'] > 0"),
            (settled, "output['open_credit'] == 0"),
        ):
            self.env["workflow.edge"].create(
                {
                    "source_node_id": apply.id,
                    "target_node_id": target.id,
                    "condition": "expression",
                    "condition_expr": expression,
                },
            )
        runtime = self._make_runtime()

        runtime.action_run_all()

        self.assertEqual(self._line(runtime, review).state, "done")
        self.assertEqual(self._line(runtime, settled).state, "skipped")

    def test_a_document_step_reports_the_document_it_issued(self):
        step = self._document_step()
        runtime = self._make_runtime()

        runtime.action_next_step()

        line = self._line(runtime, step)
        document = line.created_record_ref
        self.assertEqual(line.output["document"], document.display_name)
        self.assertEqual(line.output["amount"], 100.0)
        self.assertEqual(line.output["partner"], self.partner.display_name)
        self.assertTrue(line.output_summary)

    def test_the_register_step_reports_the_money_that_came_in(self):
        st_line = self._statement_line(amount=250.0)
        step = self._typed_step("workflow_register_statement")
        runtime = self._make_runtime(st_line_id=st_line.id)

        runtime.action_next_step()

        output = self._line(runtime, step).output
        self.assertEqual(output["amount"], 250.0)
        self.assertEqual(output["date"], "2026-08-21")

    def test_the_change_partner_step_reports_who_the_document_went_to(self):
        refund = self._document_step(
            self.template_refund,
            name="Credit note",
            workflow_partner_source="third_party",
        )
        change = self._typed_step(
            "workflow_change_partner",
            name="Change partner",
            predecessors=refund,
        )
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        runtime.action_run_all()

        output = self._line(runtime, change).output
        self.assertTrue(output["changed"])
        self.assertEqual(output["partner"], self.partner.display_name)


@tagged("post_install", "-at_install")
class TestRunPreflight(TypedStepCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template_payment = cls.env["account.move.template"].create(
            {
                "name": "TEST - Customer Payment",
                "journal_code": cls.journal_bank.code,
                "is_payment": True,
                "payment_type": "inbound",
                "partner_type": "customer",
            },
        )

    def _payment_workflow(self):
        first = self._typed_step("code", name="First", code="pass")
        payment = self._document_step(
            self.template_payment,
            name="Payment",
            predecessors=first,
            workflow_partner_source="third_party",
            workflow_auto_post=False,
        )
        last = self._document_step(
            self.template_refund,
            name="Credit note",
            predecessors=payment,
            workflow_auto_post=False,
        )
        return first, payment, last

    def _wizard(self, **vals):
        return self.env["wizard.account.bank.statement.line.start.automation"].create(
            {
                "automation_id": self.automation.id,
                "partner_id": self.partner.id,
                "amount": 100.0,
                **vals,
            },
        )

    def test_a_run_that_can_complete_reports_nothing(self):
        self._payment_workflow()

        runtime = self._make_runtime()

        self.assertFalse(runtime.problem_message)

    def test_a_run_missing_what_a_step_needs_says_so_before_it_starts(self):
        self._payment_workflow()

        wizard = self._wizard(amount=0.0)

        self.assertIn("Payment", wizard.problem_message)
        self.assertIn("no amount", wizard.problem_message)

        wizard.amount = 100.0

        self.assertFalse(wizard.problem_message)

    def test_the_wizard_shows_who_each_document_goes_to(self):
        self._payment_workflow()

        wizard = self._wizard(third_party_id=self.third_party.id)

        preview = str(wizard.plan_preview)
        payment_row, refund_row = preview.split("<li>")[2:4]
        self.assertIn("Payment", payment_row)
        self.assertIn(self.third_party.name, payment_row)
        self.assertIn("Credit note", refund_row)
        self.assertIn(self.partner.name, refund_row)
        self.assertIn(self.company.name, refund_row)

    @mute_logger(LINE_LOGGER)
    def test_a_failed_step_is_repaired_on_the_run_and_retried(self):
        first, payment, last = self._payment_workflow()
        runtime = self._make_runtime(amount=0.0)
        runtime.action_next_step()

        runtime.action_next_step()

        self.assertEqual(runtime.state, "error")
        self.assertEqual(self._line(runtime, first).state, "done")
        self.assertEqual(self._line(runtime, payment).state, "error")
        self.assertIn("needs an amount", self._line(runtime, payment).error_message)
        self.assertEqual(self._line(runtime, last).state, "waiting")
        self.assertIn("Payment", runtime.problem_message)

        runtime.amount = 100.0
        runtime.action_retry()

        self.assertFalse(runtime.problem_message)
        self.assertEqual(self._line(runtime, payment).state, "done")
        self.assertEqual(
            self._line(runtime, payment).created_record_ref.amount,
            100.0,
        )
        self.assertEqual(self._line(runtime, last).state, "ready")
        self.assertEqual(runtime.state, "in_progress")

    def test_a_settled_step_no_longer_counts_against_the_run(self):
        _first, payment, _last = self._payment_workflow()
        runtime = self._make_runtime()
        runtime.action_next_step()
        runtime.action_next_step()
        self.assertEqual(self._line(runtime, payment).state, "done")

        runtime.amount = 0.0

        self.assertFalse(
            runtime.problem_message,
            "the payment exists; what it needed is no longer a problem",
        )

    def test_the_run_diagram_says_what_each_step_does_on_this_run(self):
        _first, invoice, last = self._payment_workflow()
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        graph = runtime.get_workflow_graph()

        details = {node["id"]: node["detail"] for node in graph["nodes"]}
        self.assertIn(self.third_party.name, details[invoice.id])
        self.assertIn(self.partner.name, details[last.id])
        self.assertIn(self.company.name, details[last.id])

    def test_a_reader_without_the_workflow_s_rights_still_opens_the_run(self):
        self._payment_workflow()
        runtime = self._make_runtime()
        reader = self.env["res.users"].create(
            {
                "name": "Run Reader",
                "login": "run_reader_taa",
                "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
            },
        )

        as_reader = runtime.with_user(reader)

        self.assertFalse(as_reader.problem_message)
        self.assertEqual(len(as_reader.get_workflow_graph()["nodes"]), 3)

    def test_the_definition_diagram_says_what_each_step_is_set_to_do(self):
        _first, invoice, last = self._payment_workflow()

        graph = self.automation.get_workflow_graph()

        details = {node["id"]: node["detail"] for node in graph["nodes"]}
        self.assertIn(self.template_refund.name, details[last.id])
        self.assertIn("Third Party", details[invoice.id])
