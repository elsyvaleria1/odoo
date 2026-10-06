from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestOptionalIntegrations(AutomationAccountCommon):
    def test_create_move_from_template_without_the_optional_modules(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()

        move = step.create_move_from_template(runtime.line_ids, self.template_invoice)

        self.assertEqual(move._name, "account.move")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.partner_id, self.partner)

    def test_telegram_data_lookup_answers_with_a_mapping(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()

        self.assertEqual(step._get_runtime_telegram_data(runtime), {})

    def test_telegram_data_lookup_tolerates_a_missing_model(self):
        step = self._make_step("pass")
        runtime = self._make_runtime()

        if "approval.request" in self.env:
            self.skipTest("`approval` is installed here; the guard is the other branch")

        self.assertEqual(step._get_runtime_telegram_data(runtime), {})
