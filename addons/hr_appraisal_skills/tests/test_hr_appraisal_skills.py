from datetime import date, datetime

from dateutil.relativedelta import relativedelta

from odoo.fields import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestHrAppraisalSkills(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.user = cls.env["res.users"].create(
            {
                "name": "Michael Hawkins",
                "login": "test",
                "group_ids": [
                    (6, 0, [cls.env.ref("hr_appraisal.group_hr_appraisal_user").id])
                ],
                "notification_type": "email",
            }
        )
        cls.hr_employee, cls.hr_employee_2 = cls.env["hr.employee"].create(
            [
                {
                    "name": "Michael Hawkins",
                    "user_id": cls.user.id,
                },
                {
                    "name": "Michel Jardin",
                },
            ]
        )
        cls.hr_employee_2.parent_id = cls.hr_employee

        cls.appraisal = cls.env["hr.appraisal"].create(
            {
                "employee_id": cls.hr_employee_2.id,
                "state": "2_pending",
                "date_close": date.today() + relativedelta(months=1),
            }
        )

        cls.skill_type = cls.env["hr.skill.type"].create({"name": "Test Skill Type"})
        cls.skill_level_1, cls.skill_level_2, cls.skill_level_3 = cls.env[
            "hr.skill.level"
        ].create(
            [
                {
                    "name": "Level 1",
                    "skill_type_id": cls.skill_type.id,
                    "level_progress": 0,
                },
                {
                    "name": "Level 2",
                    "skill_type_id": cls.skill_type.id,
                    "level_progress": 50,
                },
                {
                    "name": "Level 3",
                    "skill_type_id": cls.skill_type.id,
                    "level_progress": 100,
                },
            ]
        )
        cls.skill = cls.env["hr.skill"].create(
            {"name": "Test Skill", "skill_type_id": cls.skill_type.id}
        )

        cls.appraisal_skill = cls.env["hr.appraisal.skill"].create(
            {
                "skill_type_id": cls.skill_type.id,
                "skill_id": cls.skill.id,
                "skill_level_id": cls.skill_level_1.id,
                "appraisal_id": cls.appraisal.id,
                "valid_from": datetime.today() - relativedelta(months=1),
                "justification": "This value should not change",
            }
        )

    def test_changing_skill_level_preserves_justification_value(self):
        appraisal_form = Form(self.appraisal.with_context(uid=self.user.id))
        old_skills = self.appraisal.appraisal_skill_ids
        index = self.appraisal.current_appraisal_skill_ids.ids.index(
            self.appraisal_skill.id
        )
        with appraisal_form.current_appraisal_skill_ids.edit(index) as cas:
            cas.skill_level_id = self.skill_level_2
        appraisal_form.save()
        new_skill = self.appraisal.appraisal_skill_ids - old_skills

        self.assertTrue(
            new_skill, "Editing an active/core field should create a new skill/record."
        )
        self.assertEqual(
            new_skill.justification,
            "This value should not change",
            "The justification value should be 'This value should not change'",
        )
        self.assertEqual(
            new_skill.justification,
            old_skills.justification,
            "The new and old skill should have the same value for the 'Justification' field",
        )

    def test_changing_justification_value_should_not_create_new_skill(self):
        appraisal_form = Form(self.appraisal.with_context(uid=self.user.id))
        old_skills = self.appraisal.appraisal_skill_ids
        index = self.appraisal.current_appraisal_skill_ids.ids.index(
            self.appraisal_skill.id
        )
        with appraisal_form.current_appraisal_skill_ids.edit(index) as cas:
            cas.justification = "This should NOT create a new skill"
        appraisal_form.save()
        new_skill = self.appraisal.appraisal_skill_ids - old_skills

        self.assertFalse(
            new_skill, "Editing a passive field should NOT create a new skill/record."
        )
        self.assertEqual(
            old_skills.justification,
            "This should NOT create a new skill",
            "The justification should have changed to 'This should NOT create a new skill'",
        )

    def test_create_appraisal_skill_without_hr_right(self):
        user_without_hr_right = self.env["res.users"].create(
            {
                "name": "Test without hr right",
                "login": "test_without_hr_right",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
                "notification_type": "email",
            }
        )
        user_without_hr_right.action_create_employee()
        employee_1 = self.env["hr.employee"].create(
            [
                {
                    "name": "Emp1",
                    "parent_id": user_without_hr_right.employee_ids[0].id,
                }
            ]
        )
        self.env["hr.employee.skill"].create(
            {
                "skill_type_id": self.skill_type.id,
                "skill_id": self.skill.id,
                "skill_level_id": self.skill_level_1.id,
                "employee_id": employee_1.id,
                "valid_from": date(2024, 3, 2),
            }
        )
        with self.with_user(user_without_hr_right.login):
            appraisal_form = Form(self.env["hr.appraisal"])
            appraisal_form.employee_id = employee_1
            employee_1_appraisal = appraisal_form.save()
            employee_1_appraisal.action_confirm()
            self.assertEqual(
                employee_1_appraisal.appraisal_skill_ids[0].manager_ids,
                user_without_hr_right.employee_ids[0],
            )

    def test_completing_an_appraisal_touches_only_the_skills_it_changed(self):
        kept, changed = self.env["hr.skill"].create(
            [
                {"name": "Kept skill", "skill_type_id": self.skill_type.id},
                {"name": "Changed skill", "skill_type_id": self.skill_type.id},
            ]
        )
        since = date.today() - relativedelta(years=1)
        employee = self.env["hr.employee"].create({"name": "Appraised"})
        kept_row, changed_row = self.env["hr.employee.skill"].create(
            [
                {
                    "employee_id": employee.id,
                    "skill_id": skill.id,
                    "skill_level_id": self.skill_level_1.id,
                    "skill_type_id": self.skill_type.id,
                    "valid_from": since,
                }
                for skill in (kept, changed)
            ]
        )
        appraisal = self.env["hr.appraisal"].create({"employee_id": employee.id})
        appraisal.state = "2_pending"
        appraisal_row = appraisal.current_appraisal_skill_ids.filtered(
            lambda row: row.skill_id == changed
        )
        appraisal.write(
            {
                "current_appraisal_skill_ids": [
                    Command.update(
                        appraisal_row.id, {"skill_level_id": self.skill_level_3.id}
                    )
                ]
            }
        )

        appraisal.state = "3_done"

        self.assertEqual((kept_row.valid_from, kept_row.valid_to), (since, False))
        self.assertEqual(changed_row.valid_to, date.today() - relativedelta(days=1))
        current = employee.current_employee_skill_ids
        self.assertEqual(
            {(row.skill_id, row.skill_level_id) for row in current},
            {(kept, self.skill_level_1), (changed, self.skill_level_3)},
        )
        self.assertIn(kept_row, current)


@tagged("-at_install", "post_install")
class TestAppraisalTargetJob(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.skill_type = cls.env["hr.skill.type"].create(
            {
                "name": "Target skills",
                "skill_ids": [
                    Command.create({"name": name})
                    for name in ("Alpha", "Beta", "Gamma")
                ],
                "skill_level_ids": [
                    Command.create({"name": "Solid", "level_progress": 50})
                ],
            }
        )
        skills_by_name = cls.skill_type.skill_ids.grouped("name")
        cls.alpha, cls.beta, cls.gamma = (
            skills_by_name[name] for name in ("Alpha", "Beta", "Gamma")
        )
        cls.level = cls.skill_type.skill_level_ids
        cls.job_a, cls.job_b = cls.env["hr.job"].create(
            [{"name": "Target A"}, {"name": "Target B"}]
        )
        cls.env["hr.job.skill"].create(
            [
                {
                    "job_id": job.id,
                    "skill_type_id": cls.skill_type.id,
                    "skill_id": skill.id,
                    "skill_level_id": cls.level.id,
                }
                for job, skill in (
                    (cls.job_a, cls.alpha),
                    (cls.job_a, cls.beta),
                    (cls.job_b, cls.gamma),
                )
            ]
        )
        manager = cls.env["hr.employee"].create({"name": "Target manager"})
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Target employee", "parent_id": manager.id}
        )
        cls.env["hr.employee.skill"].create(
            {
                "employee_id": cls.employee.id,
                "skill_type_id": cls.skill_type.id,
                "skill_id": cls.alpha.id,
                "skill_level_id": cls.level.id,
            }
        )
        cls.appraisal = cls.env["hr.appraisal"].create(
            {"employee_id": cls.employee.id, "manager_ids": [Command.set(manager.ids)]}
        )
        cls.appraisal.state = "2_pending"

    def _rows(self):
        return {
            (row.skill_id, row.skill_level_id)
            for row in self.appraisal.appraisal_skill_ids
        }

    def test_a_target_job_adds_a_placeholder_per_missing_skill(self):
        self.appraisal.target_job_id = self.job_a
        self.assertEqual(
            self._rows(),
            {(self.alpha, self.level), (self.beta, self.env["hr.skill.level"])},
        )

    def test_setting_the_same_target_again_keeps_the_rows(self):
        self.appraisal.target_job_id = self.job_a
        rows = self.appraisal.appraisal_skill_ids
        self.appraisal.write({"target_job_id": self.job_a.id})
        self.assertEqual(self.appraisal.appraisal_skill_ids, rows)

    def test_switching_or_clearing_the_target_replaces_the_placeholders(self):
        self.appraisal.target_job_id = self.job_a
        self.appraisal.target_job_id = self.job_b
        self.assertEqual(
            self._rows(),
            {(self.alpha, self.level), (self.gamma, self.env["hr.skill.level"])},
        )
        self.appraisal.target_job_id = False
        self.assertEqual(self._rows(), {(self.alpha, self.level)})

    def test_the_form_shows_the_placeholders_before_saving_and_saves_them_once(self):
        with Form(self.appraisal) as appraisal_form:
            appraisal_form.target_job_id = self.job_a
            self.assertEqual(len(appraisal_form.current_appraisal_skill_ids), 2)
        self.assertEqual(
            sorted(self.appraisal.appraisal_skill_ids.skill_id.mapped("name")),
            ["Alpha", "Beta"],
        )
