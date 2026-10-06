from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestRuntimeContextValue(AutomationAccountCommon):
    def setUp(self):
        super().setUp()
        self.step = self._make_step("pass")
        self.runtime = self._make_runtime()
        self.line = self.runtime.line_ids

    def test_a_real_field_is_returned(self):
        self.assertEqual(
            self.step.get_runtime_context_value(self.line, "partner_id"),
            self.partner,
        )
        self.assertEqual(
            self.step.get_runtime_context_value(self.line, "amount"),
            100.0,
        )

    def test_a_method_name_falls_through_to_the_default(self):
        for name in ("unlink", "action_cancel", "write", "create"):
            with self.subTest(name=name):
                self.assertIsNone(
                    self.step.get_runtime_context_value(self.line, name),
                )
                self.assertEqual(
                    self.step.get_runtime_context_value(self.line, name, "fallback"),
                    "fallback",
                )

    def test_an_absent_name_falls_through_to_the_default(self):
        self.assertIsNone(
            self.step.get_runtime_context_value(self.line, "nonexistent_field"),
        )
        self.assertEqual(
            self.step.get_runtime_context_value(self.line, "nonexistent_field", 7),
            7,
        )

    def test_the_module_own_fields_are_reachable(self):
        self.assertFalse(self.step.get_runtime_context_value(self.line, "st_line_id"))
        self.assertFalse(
            self.step.get_runtime_context_value(self.line, "third_party_id"),
        )
