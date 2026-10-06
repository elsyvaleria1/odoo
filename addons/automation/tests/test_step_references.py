from lxml import etree

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user

from .test_run_completion import RunCompletionCase
from .test_workflow_dag import link
from odoo.addons.automation.models._steps import collect_references, make_step_key

FORM = [
    {"name": "amount", "string": "Amount", "type": "float"},
    {"name": "note", "string": "Note", "type": "char"},
    {"name": "checked", "string": "Checked", "type": "boolean"},
]


class TestStepKeys(TransactionCase):
    def test_a_key_is_an_ascii_identifier_made_from_the_name(self):
        self.assertEqual(
            make_step_key("Conciliación bancaria", set()), "conciliacion_bancaria"
        )
        self.assertEqual(make_step_key("3 Factura", set()), "step_3_factura")
        self.assertEqual(make_step_key("", set()), "step")

    def test_a_key_steps_around_keywords_and_mapping_methods(self):
        self.assertEqual(make_step_key("If", set()), "if_step")
        self.assertEqual(make_step_key("Get", set()), "get_step")

    def test_a_taken_key_gets_a_suffix(self):
        self.assertEqual(make_step_key("BSL", {"bsl", "bsl_2"}), "bsl_3")


class TestReferenceParsing(TransactionCase):
    def test_every_literal_spelling_names_its_key(self):
        refs = collect_references(
            "a = steps.invoice.record\n"
            "b = steps['payment'].output\n"
            "c = steps.get('note')\n"
            "d = 'claim' in steps\n"
        )
        self.assertEqual(refs.keys, {"invoice", "payment", "note", "claim"})
        self.assertFalse(refs.dynamic)
        self.assertFalse(refs.uses_previous)

    def test_a_computed_index_is_dynamic(self):
        refs = collect_references("key = 'a'\nx = steps[key]")
        self.assertTrue(refs.dynamic)
        self.assertEqual(refs.keys, set())

    def test_previous_is_noticed(self):
        self.assertTrue(collect_references("x = previous.output", "exec").uses_previous)

    def test_an_expression_parses_in_eval_mode(self):
        refs = collect_references("steps.invoice.output['amount'] > 0", mode="eval")
        self.assertEqual(refs.keys, {"invoice"})

    def test_code_that_does_not_parse_names_nothing(self):
        self.assertEqual(collect_references("steps.a +").keys, set())


class StepReferenceCase(RunCompletionCase):
    def _problems(self):
        return self.automation._get_step_reference_problems()


class TestKeysOnSteps(StepReferenceCase):
    def test_a_step_is_given_a_key_from_its_name(self):
        first = self._action("Factura CX")
        second = self._action("Factura CX")

        self.assertEqual(first.step_key, "factura_cx")
        self.assertEqual(second.step_key, "factura_cx_2")

    def test_a_step_attached_to_an_automation_later_gets_a_key(self):
        loose = self.Action.create(
            {"name": "Loose Step", "model_id": self.model_partner.id, "state": "code"}
        )
        self.assertFalse(loose.step_key)

        loose.automation_rule_id = self.automation

        self.assertEqual(loose.step_key, "loose_step")

    def test_a_given_key_is_kept(self):
        self.assertEqual(
            self._action("Factura", step_key="invoice").step_key, "invoice"
        )

    def test_an_invalid_key_is_refused(self):
        for key in ("Invoice", "2nd", "a__b", "class", "items", "a-b"):
            with (
                self.subTest(key=key),
                self.assertRaises(ValidationError),
                self.env.cr.savepoint(),
            ):
                self._action("bad", step_key=key)

    def test_two_steps_of_one_automation_cannot_share_a_key(self):
        self._action("one", step_key="same")
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self._action("two", step_key="same")

    def test_a_copied_step_gets_a_key_of_its_own(self):
        original = self._action("Invoice", step_key="invoice")

        self.assertNotEqual(original.copy().step_key, "invoice")

    def test_a_step_copied_into_its_own_automation_by_name_gets_a_new_key(self):
        original = self._action("Invoice", step_key="invoice")

        copy = original.copy({"automation_rule_id": self.automation.id})

        self.assertNotEqual(copy.step_key, "invoice")

    def test_a_copied_automation_keeps_its_keys(self):
        invoice = self._action("Invoice", step_key="invoice")
        reader = self._action("Reader", "x = steps.invoice.output")
        link(self.env, invoice, reader)

        copy = self.automation.copy()

        self.assertEqual(
            sorted(copy.action_server_ids.mapped("step_key")),
            ["invoice", "reader"],
        )
        self.assertFalse(copy._get_step_reference_problems())


class TestReferenceProblems(StepReferenceCase):
    def test_reading_an_upstream_step_is_fine(self):
        invoice = self._action("Invoice", step_key="invoice")
        middle = self._action("Middle")
        reader = self._action("Reader", "x = steps.invoice.output")
        link(self.env, invoice, middle)
        link(self.env, middle, reader)

        self.assertEqual(self._problems(), [])

    def test_reading_a_parallel_step_is_a_problem(self):
        self._action("Invoice", step_key="invoice")
        self._action("Reader", "x = steps.invoice.output")

        self.assertRegex(self._problems()[0], "not upstream of it")

    def test_reading_an_unknown_key_is_a_problem(self):
        self._action("Reader", "x = steps.nobody.output")

        self.assertRegex(self._problems()[0], "no step of this automation")

    def test_reading_itself_is_a_problem(self):
        self._action("Reader", "x = steps.reader.output")

        self.assertRegex(self._problems()[0], "which is itself")

    def test_previous_at_a_join_is_a_problem(self):
        left = self._action("Left")
        right = self._action("Right")
        join = self._action("Join", "x = previous.output")
        link(self.env, left, join)
        link(self.env, right, join)

        self.assertRegex(self._problems()[0], "2 steps lead to it")

    def test_an_edge_may_read_its_source_and_what_is_above_it(self):
        invoice = self._action("Invoice")
        check = self._action("Check")
        after = self._action("After")
        link(self.env, invoice, check)
        link(
            self.env,
            check,
            after,
            condition="expression",
            condition_expr="steps.invoice.state == 'done' and steps.check.state == 'done'",
        )

        self.assertEqual(self._problems(), [])

    def test_an_edge_reading_a_step_below_its_source_is_a_problem(self):
        first = self._action("First")
        after = self._action("After")
        link(
            self.env,
            first,
            after,
            condition="expression",
            condition_expr="steps.after.state == 'done'",
        )

        self.assertRegex(self._problems()[0], "neither 'First' nor upstream")

    def test_the_automation_shows_its_problems(self):
        self._action("Reader", "x = steps.nobody.output")

        self.automation.invalidate_recordset(["step_reference_warning"])
        self.assertIn("nobody", self.automation.step_reference_warning)

    def test_no_run_starts_while_a_problem_is_left(self):
        self._action("Reader", "x = steps.nobody.output")

        with self.assertRaisesRegex(UserError, "cannot start or update a run"):
            self._run()

    def test_checking_a_run_needs_no_right_to_read_step_code(self):
        invoice = self._action("Invoice", step_key="invoice")
        reader = self._action("Reader", "x = steps.invoice.output")
        link(self.env, invoice, reader)
        clerk = new_test_user(
            self.env, login="workflow_clerk", groups="base.group_user"
        )

        self.automation.with_user(clerk)._check_runnable_references()

    def test_a_step_read_by_another_cannot_be_renamed_or_removed(self):
        invoice = self._action("Invoice", step_key="invoice")
        reader = self._action("Reader", "x = steps.invoice.output")
        link(self.env, invoice, reader)

        with self.assertRaisesRegex(ValidationError, "Reader"):
            invoice.step_key = "bill"
        with self.assertRaisesRegex(ValidationError, "Reader"):
            invoice.unlink()

    def test_removing_a_step_already_gone_with_its_automation_is_harmless(self):
        step = self._action("Gone")
        self.automation.unlink()

        step.unlink()

    def test_a_step_and_its_reader_can_go_together(self):
        invoice = self._action("Invoice", step_key="invoice")
        reader = self._action("Reader", "x = steps.invoice.output")
        link(self.env, invoice, reader)

        (invoice | reader).unlink()

        self.assertFalse(self.automation.action_server_ids)


class TestStepScope(StepReferenceCase):
    def test_a_step_reads_an_upstream_step_by_key(self):
        count = self._action(
            "Count", "runtime_line._set_output({'n': 3}, 'three')", step_key="count"
        )
        middle = self._action("Middle")
        reader = self._action(
            "Reader",
            "record.write({'ref': '%s/%s' % (steps.count.output['n'], steps.count.summary)})",
        )
        link(self.env, count, middle)
        link(self.env, middle, reader)

        runtime = self._run()

        self.assertEqual(runtime.state, "done")
        self.assertEqual(self.partner.ref, "3/three")

    def test_previous_is_the_single_step_before(self):
        count = self._action("Count", "runtime_line._set_output({'n': 7})")
        reader = self._action(
            "Reader", "record.write({'ref': str(previous.output['n'])})"
        )
        link(self.env, count, reader)

        self._run()

        self.assertEqual(self.partner.ref, "7")

    def test_previous_at_a_join_is_falsy_and_explains_itself_when_read(self):
        left = self._action("Left")
        right = self._action("Right")
        join = self._action("Join")
        link(self.env, left, join)
        link(self.env, right, join)
        runtime = self._run()

        previous = self._line(runtime, join)._get_step_scope()["previous"]

        self.assertFalse(previous)
        with self.assertRaisesRegex(AttributeError, "left, right"):
            previous.output

    def test_predecessors_names_only_the_steps_with_an_edge_here(self):
        top = self._action("Top")
        middle = self._action("Middle")
        reader = self._action(
            "Reader",
            "record.write({'ref': ','.join(sorted(predecessors)) + '|' + ','.join(sorted(steps))})",
        )
        link(self.env, top, middle)
        link(self.env, middle, reader)

        self._run()

        self.assertEqual(self.partner.ref, "middle|middle,top")

    def test_a_step_cannot_rewrite_the_output_it_reads(self):
        count = self._action("Count", "runtime_line._set_output({'n': 1})")
        reader = self._action("Reader", "steps.count.output['n'] = 99")
        link(self.env, count, reader)

        runtime = self._run()

        self.assertEqual(self._line(runtime, count).output, {"n": 1})

    def test_the_record_a_step_made_is_readable_downstream(self):
        maker = self._action(
            "Maker",
            "partner = env['res.partner'].create({'name': 'Made'})\n"
            "runtime_line.write({'created_record_ref': 'automation.runtime,%s' % runtime.id})",
        )
        reader = self._action(
            "Reader", "record.write({'ref': steps.maker.record._name})"
        )
        link(self.env, maker, reader)

        self._run()

        self.assertEqual(self.partner.ref, "automation.runtime")

    def test_an_edge_branches_on_an_upstream_step(self):
        count = self._action("Count", "runtime_line._set_output({'n': 5})")
        middle = self._action("Middle")
        big = self._action("Big")
        small = self._action("Small")
        link(self.env, count, middle)
        link(
            self.env,
            middle,
            big,
            condition="expression",
            condition_expr="steps.count.output['n'] > 3",
        )
        link(
            self.env,
            middle,
            small,
            condition="expression",
            condition_expr="steps.count.output['n'] <= 3",
        )

        runtime = self._run()

        self.assertEqual(self._line(runtime, big).state, "done")
        self.assertEqual(self._line(runtime, small).state, "skipped")


class TestStepForms(StepReferenceCase):
    def _input_line_context(self, line):
        return line.with_context(automation_input_line_id=line.id)

    def test_a_step_with_a_form_asks_before_it_runs(self):
        ask = self._action(
            "Ask",
            "record.write({'ref': str(step.input['amount'])})",
            input_definition=FORM,
        )

        runtime = self._run()

        line = self._line(runtime, ask)
        self.assertEqual(line.state, "paused")
        self.assertTrue(runtime.awaiting_input)
        self.assertEqual(line._get_unanswered_questions(), ["Amount", "Note"])

    def test_the_answers_run_the_step_and_reach_later_steps(self):
        ask = self._action(
            "Ask",
            "record.write({'ref': str(step.input['amount'])})",
            input_definition=FORM,
        )
        after = self._action(
            "After", "record.write({'comment': steps.ask.input['note']})"
        )
        link(self.env, ask, after)
        runtime = self._run()
        line = self._line(runtime, ask)

        line.input_values = {"amount": 12.5, "note": "claimed"}
        self._input_line_context(line).action_submit_input()

        self.assertEqual(line.state, "done")
        self.assertEqual(self.partner.ref, "12.5")
        self.assertEqual(self._line(runtime, after).state, "ready")
        runtime.action_run_all()
        self.assertIn("claimed", str(self.partner.comment))
        self.assertEqual(runtime.state, "done")

    def test_an_unanswered_form_cannot_be_submitted(self):
        ask = self._action("Ask", input_definition=FORM)
        runtime = self._run()
        line = self._line(runtime, ask)
        line.input_values = {"amount": 3.0}

        with self.assertRaisesRegex(UserError, "Note"):
            self._input_line_context(line).action_submit_input()

    def test_the_dialog_shows_the_form(self):
        ask = self._action("Ask", input_definition=FORM)
        runtime = self._run()
        line = self._line(runtime, ask)

        action = runtime._get_input_action(line)
        arch = self._input_line_context(line).get_view(action["views"][0][0], "form")[
            "arch"
        ]

        self.assertTrue(etree.fromstring(arch).xpath("//field[@name='input_values']"))

    def test_an_input_step_with_a_form_finishes_when_answered(self):
        ask = self._action("Ask", node_type="input", input_definition=FORM)
        after = self._action("After", "record.write({'ref': steps.ask.input['note']})")
        link(self.env, ask, after)
        runtime = self._run()
        line = self._line(runtime, ask)
        self.assertEqual(line.state, "paused")

        line.input_values = {"amount": 1.0, "note": "ok"}
        self._input_line_context(line).action_submit_input()

        self.assertEqual(line.state, "done")
        self.assertEqual(self.partner.ref, "ok")

    def test_an_input_step_asks_the_run_or_a_form_not_both(self):
        field = self.env["ir.model.fields"]._get("automation.runtime", "partner_id")
        with self.assertRaisesRegex(ValidationError, "both"):
            self._action(
                "Ask",
                node_type="input",
                input_field_ids=[(6, 0, field.ids)],
                input_definition=FORM,
            )

    def test_a_wait_step_asks_its_form_before_it_waits(self):
        wait = self._action("Wait", node_type="wait", input_definition=FORM)
        runtime = self._run()
        line = self._line(runtime, wait)
        self.assertEqual(line.state, "paused")
        self.assertFalse(line.date_resume)

        line.input_values = {"amount": 1.0, "note": "go"}
        self._input_line_context(line).action_submit_input()

        self.assertEqual(line.state, "paused")
        self.assertTrue(line.date_resume)


class TestRunAnyReadyStep(StepReferenceCase):
    def _started(self):
        runtime = self.env["automation.runtime"].create(
            {
                "automation_id": self.automation.id,
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        runtime.action_start()
        return runtime

    def test_two_roots_are_both_ready_and_either_runs_first(self):
        first = self._action("First", "record.write({'ref': 'first'})")
        second = self._action("Second", "record.write({'ref': 'second'})")
        runtime = self._started()

        self._line(runtime, second).action_run()

        self.assertEqual(self.partner.ref, "second")
        self.assertEqual(self._line(runtime, second).state, "done")
        self.assertEqual(self._line(runtime, first).state, "ready")

    def test_a_step_that_is_not_ready_does_not_run(self):
        first = self._action("First")
        second = self._action("Second")
        link(self.env, first, second)
        runtime = self._started()

        with self.assertRaisesRegex(UserError, "not ready"):
            self._line(runtime, second).action_run()
