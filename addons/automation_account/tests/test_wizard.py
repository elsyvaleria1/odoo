from odoo import fields
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests.common import tagged
from odoo.tools.safe_eval import safe_eval

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestRuntimeWizard(AutomationAccountCommon):
    def setUp(self):
        super().setUp()
        self._make_chain(["pass", "pass"])

    def _make_statement_line(self, amount, ref):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.journal_bank.id,
                "payment_ref": ref,
                "partner_id": self.partner.id,
                "amount": amount,
                "date": fields.Date.to_date("2026-08-21"),
            },
        )

    def _other_workflow(self):
        other = self.env["automation.rule"].create(
            {
                "name": "TEST - Other workflow",
                "model_id": self.model_line.id,
                "trigger": "on_hand",
            },
        )
        self._make_step("pass", automation=other)
        return other

    def _make_wizard(self, **vals):
        wizard_vals = {
            "automation_id": self.automation.id,
            "partner_id": self.partner.id,
            "amount": 1500.0,
        }
        wizard_vals.update(vals)
        return self.env["wizard.account.bank.statement.line.start.automation"].create(
            wizard_vals
        )

    def test_wizard_create_basic(self):
        wizard = self._make_wizard()

        self.assertEqual(wizard.automation_id, self.automation)
        self.assertEqual(wizard.partner_id, self.partner)
        self.assertEqual(wizard.amount, 1500.0)

    def test_wizard_creates_runtime(self):
        wizard = self._make_wizard(
            amount=2500.0,
            date=fields.Date.to_date("2026-08-27"),
            reference="TEST-WIZARD-001",
        )

        action = wizard.action_create_runtime()
        runtime = self.env["automation.runtime"].browse(action["res_id"])

        self.assertEqual(action["res_model"], "automation.runtime")
        self.assertEqual(runtime.automation_id, self.automation)
        self.assertEqual(runtime.partner_id, self.partner)
        self.assertEqual(runtime.amount, 2500.0)
        self.assertEqual(runtime.reference, "TEST-WIZARD-001")

    def test_wizard_from_bank_statement(self):
        st_line = self._make_statement_line(3000.0, "BANK-PAYMENT-TEST-001")

        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
            )
            .create({"automation_id": self.automation.id})
        )

        self.assertEqual(wizard.st_line_id, st_line)

        action = wizard.action_create_runtime()
        runtime = self.env["automation.runtime"].browse(action["res_id"])

        self.assertEqual(runtime.st_line_id, st_line)

    def test_wizard_default_values(self):
        st_line = self._make_statement_line(3000.0, "BANK-DEFAULTS-001")

        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
            )
            .create({"automation_id": self.automation.id})
        )

        self.assertEqual(wizard.partner_id, self.partner)
        self.assertEqual(wizard.reference, "BANK-DEFAULTS-001")
        self.assertEqual(wizard.amount, 3000.0)
        self.assertEqual(wizard.date, st_line.date)

    def test_wizard_runtime_starts_workflow(self):
        wizard = self._make_wizard()

        action = wizard.action_create_runtime()
        runtime = self.env["automation.runtime"].browse(action["res_id"])

        self.assertEqual(runtime.state, "in_progress")
        self.assertEqual(len(runtime.line_ids), 2)

    def test_wizard_third_party(self):
        wizard = self._make_wizard(third_party_id=self.third_party.id)

        action = wizard.action_create_runtime()
        runtime = self.env["automation.runtime"].browse(action["res_id"])

        self.assertEqual(runtime.third_party_id, self.third_party)

    def test_the_customer_an_approval_names_is_the_run_s_partner(self):
        customer = self.env["res.partner"].create({"name": "Automation Real Customer"})
        st_line = self._make_statement_line(3000.0, "BANK-THIRD-PARTY-001")

        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
                default_partner_id=customer.id,
            )
            .create({"automation_id": self.automation.id})
        )

        self.assertEqual(wizard.partner_id, customer)
        self.assertEqual(
            wizard.third_party_id,
            self.partner,
            "the partner the line was booked to stands in for the customer",
        )

    def test_a_line_booked_to_the_customer_names_no_third_party(self):
        st_line = self._make_statement_line(3000.0, "BANK-THIRD-PARTY-002")

        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
                default_partner_id=self.partner.id,
            )
            .create({"automation_id": self.automation.id})
        )

        self.assertEqual(wizard.partner_id, self.partner)
        self.assertFalse(wizard.third_party_id)

    def test_wizard_opens_runtime_form(self):
        wizard = self._make_wizard()

        action = wizard.action_create_runtime()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "automation.runtime")
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["target"], "current")
        self.assertFalse(action["context"]["create"])

    def test_the_run_takes_every_company_chosen_in_the_wizard(self):
        other = self.env["res.company"].create({"name": "Second Co"})
        self.env.user.company_ids |= other
        both = self.company | other

        wizard = self._make_wizard(company_ids=[Command.set(both.ids)])
        action = wizard.action_create_runtime()
        runtime = self.env["automation.runtime"].browse(action["res_id"])

        self.assertEqual(runtime.company_ids, both)

    def test_the_wizard_starts_in_the_bank_line_s_company(self):
        st_line = self._make_statement_line(3000.0, "BANK-COMPANY-001")

        wizard = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            .with_context(
                active_model="account.bank.statement.line",
                active_id=st_line.id,
            )
            .create({"automation_id": self.automation.id})
        )

        self.assertEqual(wizard.company_ids, st_line.company_id)

    def test_the_link_hook_is_called(self):
        seen = []
        self.patch(
            type(self.env["wizard.account.bank.statement.line.start.automation"]),
            "_link_approval_request",
            lambda self, runtime: seen.append(runtime),
        )

        self._make_wizard().action_create_runtime()

        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]._name, "automation.runtime")

    def test_workflow_choices_offer_the_manual_rules(self):
        domain = (
            self.env["wizard.account.bank.statement.line.start.automation"]
            ._fields["automation_id"]
            .domain
        )

        choices = self.env["automation.rule"].search(
            safe_eval(domain, {"started_automation_ids": []}),
        )

        self.assertIn(self.automation, choices)

    def test_statement_line_points_to_its_latest_live_workflow(self):
        st_line = self._make_statement_line(1500.0, "TEST-RUN-LINK")
        self.assertFalse(st_line.automation_runtime_id)

        other = self._other_workflow()
        first = self._make_runtime(st_line_id=st_line.id)
        second = self._make_runtime(automation=other, st_line_id=st_line.id)
        self.assertEqual(st_line.automation_runtime_id, second)

        second.action_cancel()
        self.assertEqual(st_line.automation_runtime_id, first)
        self.assertEqual(st_line.automation_runtime_state, first.state)

    def test_a_run_finishing_refreshes_the_state_its_statement_line_shows(self):
        st_line = self._make_statement_line(1500.0, "TEST-RUN-STATE")
        runtime = self._make_runtime(st_line_id=st_line.id)
        self.assertEqual(st_line.automation_runtime_state, "in_progress")

        runtime.action_run_all()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(st_line.automation_runtime_id, runtime)
        self.assertEqual(st_line.automation_runtime_state, "done")

    def _first_step(self):
        return self.automation.action_server_ids.sorted("sequence")[:1]

    def test_run_at_start_step_executes_when_the_run_starts(self):
        self._first_step().run_at_start = True
        st_line = self._make_statement_line(1500.0, "TEST-RUN-AT-START")

        runtime = self._make_runtime(st_line_id=st_line.id)

        lines = runtime.line_ids.sorted("sequence")
        self.assertEqual(lines.mapped("state"), ["done", "ready"])
        self.assertEqual(runtime.state, "in_progress")

    def test_run_at_start_waits_while_the_automation_is_paused(self):
        self._first_step().run_at_start = True
        self.automation.action_pause()
        st_line = self._make_statement_line(1500.0, "TEST-RUN-AT-START-PAUSED")

        runtime = self._make_runtime(st_line_id=st_line.id)

        self.assertEqual(runtime.line_ids.sorted("sequence")[:1].state, "ready")

    def test_run_at_start_waits_without_a_statement_line(self):
        self._first_step().run_at_start = True

        runtime = self._make_runtime()

        self.assertEqual(runtime.line_ids.sorted("sequence")[:1].state, "ready")

    def test_unflagged_first_step_waits_for_next_step(self):
        st_line = self._make_statement_line(1500.0, "TEST-NO-RUN-AT-START")

        runtime = self._make_runtime(st_line_id=st_line.id)

        self.assertEqual(runtime.line_ids.sorted("sequence")[:1].state, "ready")

    def test_a_bank_line_starts_each_workflow_once(self):
        st_line = self._make_statement_line(1500.0, "Once")
        self._make_wizard(st_line_id=st_line.id).action_create_runtime()

        with self.assertRaisesRegex(ValidationError, "starts each workflow once"):
            self._make_wizard(st_line_id=st_line.id).action_create_runtime()

    def test_a_bank_line_can_start_another_workflow(self):
        st_line = self._make_statement_line(1500.0, "Two flows")
        other = self._other_workflow()
        self._make_wizard(st_line_id=st_line.id).action_create_runtime()

        action = self._make_wizard(
            st_line_id=st_line.id,
            automation_id=other.id,
        ).action_create_runtime()

        self.assertTrue(action["res_id"])
        self.assertEqual(len(st_line.automation_runtime_ids), 2)

    def test_a_cancelled_run_frees_its_workflow_for_the_bank_line(self):
        st_line = self._make_statement_line(1500.0, "Again")
        action = self._make_wizard(st_line_id=st_line.id).action_create_runtime()
        self.env["automation.runtime"].browse(action["res_id"]).action_cancel()

        again = self._make_wizard(st_line_id=st_line.id).action_create_runtime()

        self.assertNotEqual(again["res_id"], action["res_id"])

    def test_the_wizard_no_longer_offers_a_workflow_the_line_started(self):
        st_line = self._make_statement_line(1500.0, "Offered")
        self._make_wizard(st_line_id=st_line.id).action_create_runtime()

        wizard = self._make_wizard(st_line_id=st_line.id)

        self.assertIn(self.automation, wizard.started_automation_ids)
