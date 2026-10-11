from unittest.mock import patch

from odoo import tests

DATA_FILE = ("hr_payroll", ["data/hr_salary_rule_data.xml"])


@tests.tagged("post_install", "-at_install")
class TestSalaryRuleReset(tests.TransactionCase):
    """`hr_payroll.ir_cron_update_payroll_data` re-converts the salary data of every
    installed localization once a week, so a rule a customer edits in the form has to
    be released from its data file or the edit does not survive seven days.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data_rule = cls.env.ref("hr_payroll.default_basic_salary_rule")
        cls.data_rule_imd = (
            cls.env["ir.model.data"]
            .sudo()
            .search(
                [("model", "=", "hr.salary.rule"), ("res_id", "=", cls.data_rule.id)]
            )
        )
        cls.assertTrue(cls.data_rule_imd, "the fixture rule must come from a data file")

    def _run_the_weekly_update(self):
        with patch.object(
            type(self.env["hr.payslip"]),
            "_get_data_files_to_update",
            lambda payslips: [DATA_FILE],
            create=True,
        ):
            self.env["hr.payslip"].sudo()._update_payroll_data()

    def test_the_weekly_update_keeps_a_rule_the_user_edited(self):
        self.assertFalse(self.data_rule.modified_by_user)
        self.assertFalse(self.data_rule_imd.noupdate)
        shipped_sequence = self.data_rule.sequence

        self.data_rule.sequence = shipped_sequence + 76
        self.assertTrue(
            self.data_rule.modified_by_user, "editing a shipped field claims the rule"
        )
        self.assertTrue(
            self.data_rule_imd.noupdate, "and flags its external identifier"
        )

        self._run_the_weekly_update()
        self.assertEqual(
            self.data_rule.sequence,
            shipped_sequence + 76,
            "the customer's edit has to survive the weekly data update",
        )
        self.assertTrue(
            self.data_rule_imd.noupdate, "and the flag has to survive it too"
        )

    def test_the_weekly_update_still_owns_an_untouched_rule(self):
        shipped_sequence = self.data_rule.sequence
        self.data_rule.invalidate_recordset()
        self.data_rule.with_context(install_mode=True).sequence = shipped_sequence + 76
        self.assertFalse(
            self.data_rule.modified_by_user,
            "a write from the data loader is not a user edit",
        )
        self.assertFalse(self.data_rule_imd.noupdate)

        self._run_the_weekly_update()
        self.assertEqual(
            self.data_rule.sequence,
            shipped_sequence,
            "an unclaimed rule is still maintained by its data file",
        )

    def test_reset_hands_the_rule_back_to_its_data_file(self):
        shipped_sequence = self.data_rule.sequence
        self.data_rule.sequence = shipped_sequence + 76
        self.assertTrue(self.data_rule.modified_by_user)

        with patch.object(
            type(self.env["hr.payslip"]),
            "_get_data_files_to_update",
            lambda payslips: [DATA_FILE],
            create=True,
        ):
            self.data_rule.action_reset_rule()

        self.assertEqual(
            self.data_rule.sequence,
            shipped_sequence,
            "reset re-applies the shipped value",
        )
        self.assertFalse(self.data_rule.modified_by_user)
        self.assertFalse(self.data_rule_imd.noupdate)

    def test_a_rule_the_user_created_is_never_claimed(self):
        own_rule = self.env["hr.salary.rule"].create(
            {
                "name": "Rule of our own",
                "code": "OUROWN",
                "category_id": self.env.ref("hr_payroll.ALW").id,
                "struct_id": self.data_rule.struct_id.id,
                "sequence": 500,
                "amount_select": "fix",
                "amount_fix": 1.0,
            }
        )
        own_rule.sequence = 501
        self.assertFalse(
            own_rule.modified_by_user,
            "a rule with no external identifier is the user's already; "
            "there is nothing to release",
        )
