from datetime import date, timedelta

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, new_test_user


class TestAppraisalCampaign(TransactionCase):
    """Cover the appraisal campaign wizard and the department counters."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env["hr.appraisal.template"].create(
            {"description": "Campaign template"}
        )
        cls.department = cls.env["hr.department"].create({"name": "Campaign R&D"})
        cls.manager = cls.env["hr.employee"].create(
            {"name": "Campaign Manager", "department_id": cls.department.id}
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Campaign Employee",
                "department_id": cls.department.id,
                "parent_id": cls.manager.id,
            }
        )
        cls.appraisal_date = date.today() + timedelta(days=30)

    def _make_wizard(self, **values):
        return self.env["wizard.hr.appraisal.create"].create(
            {
                "mode": "employee",
                "employee_ids": [Command.set(self.employee.ids)],
                "appraisal_template_id": self.template.id,
                "appraisal_date": self.appraisal_date,
                **values,
            }
        )

    def test_campaign_by_employee(self):
        """Check that the employee mode creates a pending appraisal run by
        the employee's manager."""
        wizard = self._make_wizard()
        action = wizard.action_generate_appraisals()

        appraisals = self.env["hr.appraisal"].search(action["domain"])
        self.assertEqual(len(appraisals), 1)
        self.assertEqual(appraisals.employee_id, self.employee)
        self.assertEqual(appraisals.manager_ids, self.manager)
        self.assertEqual(appraisals.state, "2_pending")
        self.assertEqual(appraisals.appraisal_template_id, self.template)

    def test_campaign_duplicate_reuses_existing(self):
        """Check that regenerating on the same date warns and reuses the
        existing appraisal instead of duplicating it."""
        self._make_wizard().action_generate_appraisals()

        wizard = self._make_wizard()
        self.assertIn("already have appraisals", wizard.warning)
        action = wizard.action_generate_appraisals()
        appraisals = self.env["hr.appraisal"].search(action["domain"])
        self.assertEqual(len(appraisals), 1, "No duplicate should be created")

    def test_campaign_warnings(self):
        """Check the no-employees and no-manager warnings."""
        empty_department = self.env["hr.department"].create({"name": "Empty"})
        wizard = self._make_wizard(mode="department", department_id=empty_department.id)
        self.assertIn("doesn't have employees", wizard.warning)

        orphan = self.env["hr.employee"].create({"name": "No Manager"})
        wizard = self._make_wizard(employee_ids=[Command.set(orphan.ids)])
        self.assertIn("don't have a manager", wizard.warning)
        # No manager -> no appraisal is created either
        action = wizard.action_generate_appraisals()
        self.assertFalse(self.env["hr.appraisal"].search(action["domain"]))

    def test_campaign_modes_select_employees(self):
        """Check the employee selection of company/department/category
        modes."""
        wizard = self._make_wizard(mode="department", department_id=self.department.id)
        self.assertEqual(
            wizard._get_employees_from_mode(), self.manager | self.employee
        )

        wizard = self._make_wizard(mode="company", company_id=self.env.company.id)
        self.assertIn(self.employee, wizard._get_employees_from_mode())

        category = self.env["res.partner.tag"].create({"name": "Campaign Tag"})
        self.employee.tag_ids = category
        wizard = self._make_wizard(mode="category", tag_id=category.id)
        self.assertEqual(wizard._get_employees_from_mode(), self.employee)

    def test_campaign_manager_person_excludes_self(self):
        """Check the specific-person mode, including that an employee never
        manages their own appraisal."""
        wizard = self._make_wizard(
            manager="person", manager_ids=[Command.set(self.manager.ids)]
        )
        action = wizard.action_generate_appraisals()
        appraisals = self.env["hr.appraisal"].search(action["domain"])
        self.assertEqual(appraisals.manager_ids, self.manager)

        wizard = self._make_wizard(
            employee_ids=[Command.set(self.manager.ids)],
            manager="person",
            manager_ids=[Command.set(self.manager.ids)],
        )
        action = wizard.action_generate_appraisals()
        self.assertFalse(
            self.env["hr.appraisal"].search(action["domain"]),
            "An employee must not run their own appraisal",
        )

    def test_department_to_process_counter(self):
        """Check the to-process appraisal counter of the department."""
        self.assertEqual(self.department.appraisals_to_process_count, 0)
        self.env["hr.appraisal"].create(
            {
                "employee_id": self.employee.id,
                "manager_ids": self.manager.ids,
                "date_close": self.appraisal_date,
            }
        )
        self.assertEqual(
            self.department.appraisals_to_process_count,
            1,
            "The counter invalidates on its own now that the compute declares "
            "its dependencies",
        )
        # NOTE: hr_department.action_view_appraisals is not asserted — it
        # has no callers (tracked in task t24255).

    def test_campaign_modes_without_hr_right(self):
        """A plain internal user can run a campaign in every mode.

        The `hr_appraisal_campaign_responsible` rule used to be keyed on
        `employee_ids`, a field the wizard has not filled in yet in company,
        department and category mode, so all three raised `AccessError` for
        anyone but an Appraisal Officer - behind a list button granted to every
        internal user. Only the `employee` mode was covered before.
        """
        user = new_test_user(
            self.env, login="campaign_plain_user", groups="base.group_user"
        )
        manager = self.env["hr.employee"].create(
            {
                "name": "Campaign Plain Manager",
                "user_id": user.id,
                "department_id": self.department.id,
            }
        )
        self.employee.parent_id = manager
        Wizard = self.env["wizard.hr.appraisal.create"].with_user(user)
        for values in (
            {"mode": "company", "company_id": self.env.company.id},
            {"mode": "department", "department_id": self.department.id},
            {
                "mode": "category",
                "tag_id": self.env["res.partner.tag"]
                .create({"name": "Campaign tag"})
                .id,
            },
            {"mode": "employee", "employee_ids": [Command.set(self.employee.ids)]},
        ):
            with self.subTest(mode=values["mode"]):
                wizard = Wizard.create(
                    dict(values, appraisal_template_id=self.template.id)
                )
                # Scoped to the employees this user manages, never wider.
                self.assertLessEqual(
                    set(wizard._get_employees_from_mode().ids),
                    set(
                        self.env["hr.employee"]
                        .sudo()
                        .search([("id", "child_of", manager.id)])
                        .ids
                    ),
                )

    def test_mail_template_unlink_guard(self):
        """Check that the appraisal request templates cannot be deleted."""
        template = self.env.ref("hr_appraisal.mail_template_appraisal_reminder")
        with self.assertRaises(ValidationError):
            template.unlink()

    def test_warning_is_computed_per_record(self):
        """`_compute_warning` must iterate `self`.

        It read `self.mode` and assigned `self.warning` directly, so an
        ordinary batched create — nothing exotic, just `create([{...}, {...}])`
        — raised `Expected singleton` on the first read of `warning`.
        """
        wizards = self.env["wizard.hr.appraisal.create"].create(
            [
                {
                    "mode": "employee",
                    "employee_ids": [Command.set(self.employee.ids)],
                    "appraisal_template_id": self.template.id,
                    "appraisal_date": self.appraisal_date,
                },
                {
                    "mode": "department",
                    "department_id": self.department.id,
                    "appraisal_template_id": self.template.id,
                    "appraisal_date": self.appraisal_date,
                },
            ]
        )
        self.assertEqual(len(wizards), 2)
        # The read is the assertion: it used to raise.
        self.assertEqual(len(wizards.mapped("warning")), 2)

    def test_employees_domain_covers_every_employee_record(self):
        """A non-officer's campaign scope must span all their employee records.

        `_employees_domain` used the singular `user.employee_id`, whose compute
        is scoped to `env.company` alone, while the company half of the same
        domain widens to `env.companies`. A user holding an employee record in
        a second company therefore lost every report under it — silently, and
        for every internal user, since `base.group_user` has create on this
        wizard and both "Launch Campaign" buttons carry that group.
        """
        other_company = self.env["res.company"].create({"name": "Campaign Co B"})
        user = new_test_user(self.env, login="campaign_line_manager")
        user.write({"company_ids": [Command.link(other_company.id)]})
        self.assertFalse(
            user.has_group("hr_appraisal.group_hr_appraisal_user"),
            "the defective branch is the non-officer one",
        )

        boss_a = self.env["hr.employee"].create(
            {"name": "Boss A", "user_id": user.id, "company_id": user.company_id.id}
        )
        boss_b = self.env["hr.employee"].create(
            {"name": "Boss B", "user_id": user.id, "company_id": other_company.id}
        )
        report_a = self.env["hr.employee"].create(
            {
                "name": "Report A",
                "parent_id": boss_a.id,
                "company_id": user.company_id.id,
            }
        )
        report_b = self.env["hr.employee"].create(
            {
                "name": "Report B",
                "parent_id": boss_b.id,
                "company_id": other_company.id,
            }
        )

        wizard = (
            self.env["wizard.hr.appraisal.create"]
            .with_user(user)
            .with_context(allowed_company_ids=user.company_ids.ids)
        )
        matched = self.env["hr.employee"].search(wizard._employees_domain())

        self.assertIn(report_a, matched)
        self.assertIn(
            report_b,
            matched,
            "the report under the user's second employee record must be in scope",
        )
