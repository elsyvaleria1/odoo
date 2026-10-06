from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGoalProgressionOnCreate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create({"name": "Goal owner"})

    def _goal(self, **vals):
        return self.env["hr.appraisal.goal"].create(
            {
                "name": "Ship the release",
                "employee_ids": [Command.link(self.employee.id)],
                **vals,
            }
        )

    def test_a_goal_created_with_completed_sub_goals_is_complete(self):
        goal = self._goal(
            child_ids=[
                Command.create({"name": "Code", "progression": "100"}),
                Command.create({"name": "Docs", "progression": "100"}),
            ]
        )

        self.assertEqual(goal.progression, "100")

    def test_a_goal_without_sub_goals_starts_at_zero(self):
        self.assertEqual(self._goal().progression, "000")
