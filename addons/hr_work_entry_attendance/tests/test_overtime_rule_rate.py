from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestOvertimeRuleRate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.double_time = cls.env["hr.work.entry.type"].create(
            {"name": "Double time", "code": "DOUBLE1B", "amount_rate": 2.0}
        )

    def _ruleset_with(self, **rule_vals):
        return self.env["hr.attendance.overtime.ruleset"].create(
            {
                "name": "Ruleset",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "After 8h/day",
                            "base_off": "quantity",
                            "quantity_period": "day",
                            "expected_hours": 8.0,
                            **rule_vals,
                        }
                    )
                ],
            }
        )

    def test_a_rule_created_with_a_work_entry_type_pays_that_types_rate(self):
        ruleset = self._ruleset_with(work_entry_type_id=self.double_time.id)

        self.assertEqual(ruleset.rule_ids.amount_rate, 2.0)

    def test_an_explicit_rate_wins_over_the_work_entry_type(self):
        ruleset = self._ruleset_with(
            work_entry_type_id=self.double_time.id, amount_rate=1.5
        )

        self.assertEqual(ruleset.rule_ids.amount_rate, 1.5)

    def test_a_rule_without_a_work_entry_type_pays_the_overtime_types_rate(self):
        ruleset = self._ruleset_with()

        self.assertEqual(
            ruleset.rule_ids.amount_rate,
            ruleset.rule_ids.work_entry_type_id.amount_rate,
        )
        self.assertTrue(ruleset.rule_ids.work_entry_type_id)
