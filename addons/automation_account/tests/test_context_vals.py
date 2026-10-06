from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestContextVals(AutomationAccountCommon):
    def test_use_latest_document_date_passed_as_false(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()

        move = step.create_move_from_template(
            runtime.line_ids,
            self.template_invoice,
            {"use_latest_document_date": False},
        )

        self.assertEqual(move.state, "posted")
        self.assertEqual(move.date, runtime.date)

    def test_use_latest_document_date_passed_as_true(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()

        move = step.create_move_from_template(
            runtime.line_ids,
            self.template_invoice,
            {"use_latest_document_date": True},
        )

        self.assertEqual(move.state, "posted")

    def test_control_key_is_not_forwarded_to_the_wizard(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()

        for flag in (True, False):
            with self.subTest(flag=flag):
                move = step.create_move_from_template(
                    runtime.line_ids,
                    self.template_invoice,
                    {"use_latest_document_date": flag},
                )
                self.assertEqual(move._name, "account.move")

    def test_context_vals_is_not_mutated_for_the_caller(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()
        context_vals = {"use_latest_document_date": True}

        step.create_move_from_template(
            runtime.line_ids,
            self.template_invoice,
            context_vals,
        )

        self.assertEqual(context_vals, {"use_latest_document_date": True})
