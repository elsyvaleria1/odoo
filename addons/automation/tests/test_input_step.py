from unittest.mock import patch

from lxml import etree

from odoo.exceptions import UserError, ValidationError

from .test_run_completion import RunCompletionCase
from .test_workflow_dag import link


class TestInputStep(RunCompletionCase):
    def setUp(self):
        super().setUp()
        self.field_partner = self.env["ir.model.fields"]._get(
            "automation.runtime", "partner_id"
        )
        self.ask = self._action(
            "ask",
            node_type="input",
            input_field_ids=[(6, 0, self.field_partner.ids)],
        )
        self.then = self._action(
            "then", "record.write({'ref': runtime.partner_id.name})"
        )
        link(self.env, self.ask, self.then)
        self.customer = self.env["res.partner"].create({"name": "Claimant"})

    def _run_line_context(self, runtime):
        return runtime.with_context(
            automation_input_line_id=self._line(runtime, self.ask).id,
        )

    def test_an_input_step_without_fields_is_refused(self):
        with self.assertRaises(ValidationError):
            self._action("empty", node_type="input")

    def test_an_input_step_waits_for_its_fields(self):
        runtime = self._run()

        self.assertEqual(self._line(runtime, self.ask).state, "paused")
        self.assertEqual(self._line(runtime, self.then).state, "waiting")
        self.assertEqual(runtime.state, "waiting_resume")
        self.assertTrue(runtime.awaiting_input)

    def test_the_resume_cron_does_not_release_an_input_step(self):
        runtime = self._run()

        self.env["automation.runtime"]._resume_waiting_executions()

        self.assertEqual(self._line(runtime, self.ask).state, "paused")

    def test_continuing_without_the_fields_is_refused(self):
        runtime = self._run()

        with self.assertRaisesRegex(UserError, "still needs"):
            self._run_line_context(runtime).action_submit_input()
        self.assertEqual(self._line(runtime, self.ask).state, "paused")

    def test_the_filled_in_fields_reach_the_next_steps(self):
        runtime = self._run()

        runtime.partner_id = self.customer
        self._run_line_context(runtime).action_submit_input()

        self.assertEqual(self._line(runtime, self.ask).state, "done")
        self.assertEqual(self._line(runtime, self.then).state, "done")
        self.assertEqual(self.partner.ref, "Claimant")
        self.assertEqual(runtime.state, "done")
        self.assertFalse(runtime.awaiting_input)

    def test_a_step_no_longer_waiting_takes_no_input(self):
        runtime = self._run()
        runtime.partner_id = self.customer
        submitting = self._run_line_context(runtime)
        submitting.action_submit_input()

        with self.assertRaisesRegex(UserError, "no longer waiting"):
            submitting.action_submit_input()

    def test_the_input_form_asks_for_the_step_fields(self):
        runtime = self._run()

        action = runtime.action_provide_input()
        view_id = action["views"][0][0]
        arch = runtime.with_context(**action["context"]).get_views([(view_id, "form")])[
            "views"
        ]["form"]["arch"]

        fields = etree.fromstring(arch).xpath("//group[@name='input_fields']/field")
        self.assertEqual(fields[0].get("name"), "partner_id")
        self.assertEqual(fields[0].get("required"), "1")

    def test_the_input_form_of_another_step_asks_for_its_own_fields(self):
        field_date = self.env["ir.model.fields"]._get("automation.runtime", "date")
        self.ask.input_field_ids = [(6, 0, field_date.ids)]
        runtime = self._run()

        action = runtime.action_provide_input()
        arch = runtime.with_context(**action["context"]).get_views(
            [(action["views"][0][0], "form")]
        )["views"]["form"]["arch"]

        names = etree.fromstring(arch).xpath(
            "//group[@name='input_fields']/field/@name"
        )
        self.assertEqual(names, ["date"])

    def test_cancelling_a_run_cancels_its_input_step(self):
        runtime = self._run()

        runtime.action_cancel()

        self.assertEqual(self._line(runtime, self.ask).state, "cancel")
        self.assertFalse(runtime.awaiting_input)


class TestStepInputs(RunCompletionCase):
    def setUp(self):
        super().setUp()
        self.needed = self.env["ir.model.fields"]._get(
            "automation.runtime.line", "output_summary"
        )
        self.bill = self._action(
            "bill", "record.write({'ref': runtime_line.output_summary})"
        )
        self.after = self._action("after")
        link(self.env, self.bill, self.after)
        needed = self.needed
        bill = self.bill
        original = type(self.Action)._get_line_input_fields

        def line_input_fields(action):
            return needed if action == bill else original(action)

        patcher = patch.object(
            type(self.Action), "_get_line_input_fields", line_input_fields
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _start(self):
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()
        return runtime

    def test_a_step_missing_its_fields_waits_instead_of_running(self):
        runtime = self._start()

        action = runtime.action_next_step()

        line = self._line(runtime, self.bill)
        self.assertEqual(line.state, "paused")
        self.assertFalse(self.partner.ref)
        self.assertTrue(runtime.awaiting_input)
        self.assertEqual(action["res_model"], "automation.runtime.line")
        self.assertEqual(action["res_id"], line.id)

    def test_filling_them_in_runs_that_step_and_no_more(self):
        runtime = self._start()
        action = runtime.action_next_step()
        line = self._line(runtime, self.bill)

        line.output_summary = "Family A"
        line.with_context(**action["context"]).action_submit_input()

        self.assertEqual(line.state, "done")
        self.assertEqual(self.partner.ref, "Family A")
        self.assertEqual(self._line(runtime, self.after).state, "ready")
        self.assertEqual(runtime.state, "in_progress")

    def test_continuing_without_them_is_refused(self):
        runtime = self._start()
        action = runtime.action_next_step()
        line = self._line(runtime, self.bill)

        with self.assertRaisesRegex(UserError, "still needs"):
            line.with_context(**action["context"]).action_submit_input()
        self.assertEqual(line.state, "paused")

    def test_a_step_given_them_beforehand_runs_at_once(self):
        runtime = self._start()
        self._line(runtime, self.bill).output_summary = "Family B"

        runtime.action_next_step()

        self.assertEqual(self._line(runtime, self.bill).state, "done")
        self.assertEqual(self.partner.ref, "Family B")

    def test_the_run_s_button_opens_the_step_s_dialog(self):
        runtime = self._start()
        runtime.action_next_step()

        action = runtime.action_provide_input()

        self.assertEqual(action["res_model"], "automation.runtime.line")
        arch = (
            self.env["automation.runtime.line"]
            .with_context(**action["context"])
            .get_views([(action["views"][0][0], "form")])["views"]["form"]["arch"]
        )
        names = etree.fromstring(arch).xpath(
            "//group[@name='input_fields']/field/@name"
        )
        self.assertEqual(names, ["output_summary"])

    def test_an_unattended_run_waits_for_them(self):
        runtime = self._run()

        self.assertEqual(self._line(runtime, self.bill).state, "paused")
        self.assertEqual(runtime.state, "waiting_resume")
        self.env["automation.runtime"]._resume_waiting_executions()
        self.assertEqual(self._line(runtime, self.bill).state, "paused")
