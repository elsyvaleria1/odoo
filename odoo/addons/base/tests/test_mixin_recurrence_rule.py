from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestRecurrenceRuleUntil(TransactionCase):
    def test_a_rule_repeating_until_no_date_is_refused(self):
        rule = self.env["mixin.recurrence.rule"].new(
            {"repeat_type": "until", "repeat_until": False}
        )
        with self.assertRaises(ValidationError):
            rule._check_repeat_until()

    def test_a_rule_repeating_until_a_date_is_accepted(self):
        self.env["mixin.recurrence.rule"].new(
            {"repeat_type": "until", "repeat_until": date(2030, 1, 1)}
        )._check_repeat_until()
