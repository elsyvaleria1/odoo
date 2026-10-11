from datetime import date, timedelta

from odoo.tests import freeze_time
from odoo.tests.common import TransactionCase, tagged

FROZEN_TODAY = date(2026, 6, 15)


@freeze_time("2026-06-15")
@tagged("post_install", "-at_install")
class TestAppraisalGoalSkills(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.skill_type = cls.env["hr.skill.type"].create({"name": "Languages"})
        cls.skill = cls.env["hr.skill"].create(
            {"name": "Python", "skill_type_id": cls.skill_type.id}
        )
        cls.skill_sql = cls.env["hr.skill"].create(
            {"name": "SQL", "skill_type_id": cls.skill_type.id}
        )
        cls.level = cls.env["hr.skill.level"].create(
            {
                "name": "Advanced",
                "level_progress": 75,
                "skill_type_id": cls.skill_type.id,
            }
        )
        cls.employee = cls.env["hr.employee"].create({"name": "Goal Employee"})
        cls.goal = cls.env["hr.appraisal.goal"].create(
            {"name": "Master Python", "employee_ids": [(4, cls.employee.id)]}
        )

    def _goal_skill(self, skill=None, valid_to=None):
        skill = skill or self.skill
        return self.env["hr.appraisal.goal.skill"].create(
            {
                "goal_id": self.goal.id,
                "skill_id": skill.id,
                "skill_type_id": self.skill_type.id,
                "skill_level_id": self.level.id,
                "valid_from": FROZEN_TODAY - timedelta(days=30),
                "valid_to": valid_to,
            }
        )

    def test_current_goal_skills_exclude_expired(self):
        current = self._goal_skill()
        self._goal_skill(
            skill=self.skill_sql, valid_to=FROZEN_TODAY - timedelta(days=1)
        )

        self.assertEqual(self.goal.current_goal_skill_ids, current)

    def test_search_current_goal_skills(self):
        current = self._goal_skill()
        expired = self._goal_skill(
            skill=self.skill_sql, valid_to=FROZEN_TODAY - timedelta(days=1)
        )

        goals = self.env["hr.appraisal.goal"].search(
            [("current_goal_skill_ids", "in", [current.id])]
        )
        self.assertIn(self.goal, goals)
        self.assertFalse(
            self.env["hr.appraisal.goal"].search(
                [("current_goal_skill_ids", "in", [expired.id])]
            ),
            "an expired skill must not surface its goal",
        )

    def test_search_current_goal_skills_rejects_other_operators(self):
        with self.assertRaises(NotImplementedError):
            self.env["hr.appraisal.goal"]._search_current_individual_skill_ids(
                "like", "Python"
            )

    def test_copy_recreates_skills_on_new_goal(self):
        self._goal_skill()
        copy = self.goal.copy()

        self.assertEqual(len(copy.goal_skill_ids), 1)
        self.assertEqual(copy.goal_skill_ids.skill_id, self.skill)
        self.assertNotEqual(copy.goal_skill_ids, self.goal.goal_skill_ids)
