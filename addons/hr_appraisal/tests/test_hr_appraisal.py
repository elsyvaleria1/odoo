from datetime import date

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from markupsafe import Markup

from odoo import Command
from odoo.tests import Form
from odoo.tests.common import TransactionCase


class TestHrAppraisal(TransactionCase):
    """Tests around appraisal creation (cron generation and the manual workflow)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.HrEmployee = cls.env["hr.employee"]
        cls.HrAppraisal = cls.env["hr.appraisal"]
        cls.main_company = cls.env.ref("base.main_company")

        cls.dep_rd = cls.env["hr.department"].create({"name": "RD Test"})
        cls.manager_user = cls.env["res.users"].create(
            {
                "name": "Manager User",
                "login": "manager_user",
                "password": "manager_user",
                "email": "demo@demo.com",
                "partner_id": cls.env["res.partner"]
                .create({"name": "Manager Partner"})
                .id,
            }
        )
        cls.manager = cls.env["hr.employee"].create(
            {
                "name": "Manager Test",
                "department_id": cls.dep_rd.id,
                "user_id": cls.manager_user.id,
            }
        )

        cls.job = cls.env["hr.job"].create(
            {"name": "Developer Test", "department_id": cls.dep_rd.id}
        )
        cls.colleague = cls.env["hr.employee"].create(
            {"name": "Colleague Test", "department_id": cls.dep_rd.id}
        )

        group = cls.env.ref("hr_appraisal.group_hr_appraisal_user").id
        cls.user = cls.env["res.users"].create(
            {
                "name": "Michael Hawkins",
                "login": "test",
                "group_ids": [(6, 0, [group])],
                "notification_type": "email",
            }
        )

        cls.env["ir.config_parameter"].sudo().set_param(
            "hr_appraisal.appraisal_create_in_advance_days", 8
        )
        cls.duration_after_recruitment = 6
        cls.duration_first_appraisal = 9
        cls.duration_next_appraisal = 12

        # The plan has to be configured at the same instant the employee is hired.
        # Enabling it after the freeze block recomputed next_appraisal_date against
        # the REAL clock, and `(today - 6 months) + 6 months` is not today whenever
        # the earlier month is short of that day: 2026-08-30 goes back to 2026-02-28
        # and forward to 2026-08-28, two days BEFORE today. _upcoming_appraisal_
        # creation_date then reads a date already in the past and pushes it a whole
        # period out, so these tests passed or failed on the calendar alone.
        with freeze_time(date.today() + relativedelta(months=-6)):
            cls.env.company.write(
                {
                    "appraisal_plan": True,
                    "duration_after_recruitment": cls.duration_after_recruitment,
                    "duration_first_appraisal": cls.duration_first_appraisal,
                    "duration_next_appraisal": cls.duration_next_appraisal,
                }
            )
            cls.hr_employee = cls.HrEmployee.create(
                {
                    "name": "Michael Hawkins",
                    "user_id": cls.user.id,
                    "department_id": cls.dep_rd.id,
                    "parent_id": cls.manager.id,
                    "job_id": cls.job.id,
                    "phone_ids": [
                        Command.create({"number": "+3281813700", "type": "landline"})
                    ],
                    "work_email": "michael@odoo.com",
                }
            )
            # work_location_id is a Many2one: o2m-style commands are invalid
            # and rejected by the strict ORM (they were silently dropped
            # before), so create the location explicitly.
            cls.hr_employee.write(
                {
                    "work_location_id": cls.env["hr.work.location"]
                    .create(
                        {
                            "name": "Grand-Rosière",
                            "address_id": cls.env.company.partner_id.id,
                        }
                    )
                    .id
                }
            )
        cls.appraisal_rating = cls.env["hr.appraisal.note"].create(
            {"name": "Exceeds expectations"}
        )
        cls.employee_feedback = Markup("<span>Employee Feedback</span>")
        cls.manager_feedback = Markup("<span>Manager Feedback</span>")

    def test_hr_appraisal(self):
        with freeze_time(date.today() + relativedelta(months=6)):
            # I run the scheduler
            self.env["res.company"]._run_employee_appraisal_plans()  # cronjob

            # I check whether new appraisal is created for above employee or not
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertTrue(appraisals, "Appraisal not created")

            # I start the appraisal process by click on "Start Appraisal" button.
            appraisals.action_confirm()

            # I check that state is "Appraisal Sent".
            self.assertEqual(
                appraisals.state,
                "2_pending",
                "appraisal should be 'Appraisal Sent' state",
            )

            # A final rating is needed before closing the appraisal
            appraisals.assessment_note = self.appraisal_rating
            # I close this appraisal
            appraisals.action_done()
            # I check that state of Appraisal is done.
            self.assertEqual(
                appraisals.state, "3_done", "Appraisal should be in done state"
            )

    def test_01_appraisal_next_appraisal_date(self):
        """An employee has just started working: next_appraisal_date is set properly.

        When there is an ongoing appraisal, there is no appraisal plan yet, so
        next_appraisal_date should be empty.
        """
        with freeze_time(date.today() - relativedelta(months=6)):
            months = self.hr_employee.company_id.duration_after_recruitment
            upcoming_appraisal_date = date.today() + relativedelta(months=months)

            self.assertEqual(
                self.hr_employee.next_appraisal_date,
                upcoming_appraisal_date,
                "next_appraisal_date is not set properly for an employee that has just started",
            )

            # create appraisal manually
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today() + relativedelta(months=1),
                    "state": "1_new",
                }
            )
            self.assertEqual(
                self.hr_employee.next_appraisal_date,
                False,
                "There is an ongoing appraisal for an employee, next_appraisal_date should be empty.",
            )

    def test_appraisal_next_appraisal_date_uppcoming_appraisal(self):
        """Check next_appraisal_date is correct and that the appraisal plan generates the appraisal at that time."""

        with freeze_time(date.today() - relativedelta(months=6)):
            months = self.hr_employee.company_id.duration_after_recruitment

            upcoming_appraisal_date = date.today() + relativedelta(months=months)

            self.assertEqual(
                self.hr_employee.next_appraisal_date,
                upcoming_appraisal_date,
                "next_appraisal_date is not set properly",
            )

        with freeze_time(self.hr_employee.next_appraisal_date):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertTrue(
                appraisals,
                "Appraisal not created by appraisal plan at next_appraisal_date",
            )

    def test_08_check_new_employee_no_appraisal(self):
        """
        Employee has started working recenlty
        less than duration_after_recruitment ago,
        check that appraisal is not set
        """
        with freeze_time(date.today() - relativedelta(months=3)):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertFalse(appraisals, "Appraisal created")

    def test_09_check_appraisal_after_recruitment(self):
        """
        Employee has started working recently
        Time for a first appraisal after
        some time (duration_after_recruitment) has evolved
        since recruitment
        """
        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(months=self.duration_after_recruitment)
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertTrue(appraisals, "Appraisal not created")

    def test_10_check_no_appraisal_since_recruitment_appraisal(self):
        """
        After employees first recruitment appraisal some time has evolved,
        but not enough for the first real appraisal.
        Check that appraisal is not created
        """
        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(months=self.duration_after_recruitment)
        ):
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today(),
                    "state": "3_done",
                }
            )
        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(
                months=self.duration_after_recruitment
                + self.duration_first_appraisal
                - 2
            )
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id), ("state", "=", "1_new")]
            )
            self.assertFalse(appraisals, "Appraisal created")

    def test_11_check_first_appraisal_since_recruitment_appraisal(self):
        """
        Employee started while ago, has already had
        first recruitment appraisal and now it is
        time for a first real appraisal
        """
        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(months=self.duration_after_recruitment)
        ):
            # In order to make the second appraisal, cron checks that
            # there is alraedy one done appraisal for the employee
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today(),
                    "state": "3_done",
                }
            )

        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(
                months=self.duration_after_recruitment + self.duration_first_appraisal
            )
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertTrue(appraisals, "Appraisal not created")

    def test_12_check_no_appraisal_after_first_appraisal(self):
        """
        Employee has already had first recruitment appraisal
        and first real appraisal, but its not time yet
        for recurring appraisal. Check that
        appraisal is not set
        """
        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(
                months=self.duration_after_recruitment + self.duration_first_appraisal
            )
        ):
            # In order to make recurring appraisal, cron checks that
            # there are alraedy two done appraisals for the employee
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today()
                    - relativedelta(months=self.duration_first_appraisal),
                    "state": "3_done",
                }
            )
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today(),
                    "state": "3_done",
                }
            )

        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(
                months=self.duration_after_recruitment
                + self.duration_first_appraisal
                + self.duration_next_appraisal
                - 2
            )
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id), ("state", "=", "1_new")]
            )
            self.assertFalse(appraisals, "Appraisal created")

    def test_12_check_recurring_appraisal(self):
        """
        check that recurring appraisal is created
        """
        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(
                months=self.duration_after_recruitment + self.duration_first_appraisal
            )
        ):
            # In order to make recurring appraisal, cron checks that
            # there are alraedy two done appraisals for the employee
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today()
                    - relativedelta(months=self.duration_first_appraisal),
                    "state": "3_done",
                }
            )
            self.HrAppraisal.create(
                {
                    "employee_id": self.hr_employee.id,
                    "date_close": date.today(),
                    "state": "3_done",
                }
            )

        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(
                months=self.duration_after_recruitment
                + self.duration_first_appraisal
                + self.duration_next_appraisal
            )
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertTrue(appraisals, "Appraisal not created")

    def test_load_scenario(self):
        appraisals_before = self.HrAppraisal.search_count([])
        self.env["hr.appraisal"]._load_demo_data()
        # `has_demo_data` uses this tag as its sentinel, so the scenario is only
        # really loaded if it exists afterwards.
        self.assertTrue(
            self.env.ref(
                "hr_appraisal.hr_appraisal_goal_tag_softskills",
                raise_if_not_found=False,
            ),
            "The scenario must create its goal tags",
        )
        self.assertGreater(
            self.HrAppraisal.search_count([]),
            appraisals_before,
            "The scenario must create appraisals",
        )

    def test_create_appraisal_without_hr_right(self):
        user_without_hr_right = self.env["res.users"].create(
            {
                "name": "Test without hr right",
                "login": "test_without_hr_right",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
                "notification_type": "email",
            }
        )
        user_without_hr_right.action_create_employee()
        appraisal_form = Form(
            self.env["hr.appraisal"]
            .with_user(user_without_hr_right)
            # See the note in test_hr_appraisal_goal.py: the form's modifier
            # expressions read `uid` out of the context.
            .with_context({"uid": user_without_hr_right.id})
        )
        appraisal_form.save()

    def test_create_appraisal_campaign_without_hr_right(self):
        user_without_hr_right = self.env["res.users"].create(
            {
                "name": "Test without hr right",
                "login": "test_without_hr_right",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
                "notification_type": "email",
            }
        )
        user_without_hr_right.action_create_employee()
        employees = self.env["hr.employee"].create(
            [
                {
                    "name": "Emp1",
                    "parent_id": user_without_hr_right.employee_ids[0].id,
                },
                {
                    "name": "Emp2",
                    "parent_id": user_without_hr_right.employee_ids[0].id,
                },
            ]
        )
        appraisal_template = self.env["hr.appraisal.template"].create(
            {"description": "Test appraisal template"}
        )
        appraisal_campaign_form = Form(
            self.env["wizard.hr.appraisal.create"]
            .with_user(user_without_hr_right)
            .with_context({"uid": user_without_hr_right.id})
        )
        appraisal_campaign_form.employee_ids = employees
        appraisal_campaign_form.appraisal_template_id = appraisal_template
        appraisal_campaign = appraisal_campaign_form.save()
        appraisal_campaign.action_generate_appraisals()

    def _set_appraisal_data(self, appraisal):
        appraisal.employee_feedback = self.employee_feedback
        appraisal.manager_feedback = self.manager_feedback
        appraisal.assessment_note = self.appraisal_rating

    def test_reopen_appraisal(self):
        appraisal = self.HrAppraisal.create(
            {
                "employee_id": self.hr_employee.id,
                "date_close": date.today() + relativedelta(months=1),
                "state": "2_pending",
            }
        )
        self._set_appraisal_data(appraisal)
        appraisal.action_done()
        appraisal.action_reopen()
        self.assertEqual(
            appraisal.state,
            "2_pending",
            "A reopened appraisal should be in the pending state",
        )
        self.assertEqual(
            appraisal.employee_feedback,
            self.employee_feedback,
            "Employee feedback should stay the same after the appraisal is reopened",
        )
        self.assertEqual(
            appraisal.manager_feedback,
            self.manager_feedback,
            "Manager feedback should stay the same after the appraisal is reopened",
        )
        self.assertEqual(
            appraisal.assessment_note,
            self.appraisal_rating,
            "Appraisal rating shouldn't change when an appraisal is reopened",
        )

    def _get_appraisal_count(self, user):
        return (
            self.env["hr.appraisal"]
            .with_user(user)
            .search_count(
                [
                    ("employee_id", "=", self.hr_employee.id),
                ]
            )
        )

    def test_appraisal_with_employee_officer(self):
        """
        This test checks that an admin can see appraisals of all employees,
        while an employee officer can only see appraisals where they are
        the appraiser.
        """
        admin_user = self.env.ref("base.user_admin")
        officer_group = self.env.ref("hr.group_hr_manager")
        officer_user = self.env["res.users"].create(
            {
                "name": "Employee Officer",
                "login": "employee_officer",
                "group_ids": [(6, 0, [officer_group.id])],
                "notification_type": "email",
            }
        )
        officer_user.action_create_employee()

        # Create appraisal A with admin as appraiser
        appraisal_a = self.HrAppraisal.create(
            {
                "employee_id": self.hr_employee.id,
                "manager_ids": [(6, 0, [admin_user.employee_id.id])],
                "date_close": date.today() + relativedelta(months=1),
                "state": "1_new",
            }
        )

        self.assertEqual(self._get_appraisal_count(admin_user), 1)
        self.assertEqual(self._get_appraisal_count(officer_user), 0)

        # An officer who cannot see any of this employee's appraisals must get
        # an honest empty list, not a list scoped to an empty employee id.
        action = self.hr_employee.with_user(
            officer_user
        ).action_view_employee_appraisals()
        self.assertEqual(action["domain"], [("employee_id", "in", [])])
        self.assertFalse(action.get("res_id"))

        # Create appraisal B with officer as appraiser
        self.HrAppraisal.create(
            {
                "employee_id": self.hr_employee.id,
                "manager_ids": [(6, 0, [officer_user.employee_id.id])],
                "date_close": date.today() + relativedelta(months=1),
                "state": "1_new",
            }
        )

        self.assertEqual(self._get_appraisal_count(admin_user), 2)
        self.assertEqual(self._get_appraisal_count(officer_user), 1)

        # Delete appraisal A
        appraisal_a.sudo().unlink()

        self.assertEqual(self._get_appraisal_count(admin_user), 1)
        self.assertEqual(self._get_appraisal_count(officer_user), 1)

    def test_appraisal_departement_from_employee(self):
        self.assertEqual(self.hr_employee.department_id, self.dep_rd)

        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(months=self.duration_after_recruitment)
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertEqual(appraisals.department_id, self.dep_rd)

    def test_appraisal_template_computation(self):
        # Delete all templates to prevent them from interacting with the test
        for template in self.env["hr.appraisal.template"].search([]):
            template.unlink()

        test_template = self.env["hr.appraisal.template"].create(
            {"description": "Test appraisal template"}
        )
        test_template.company_id = self.env.company
        self.hr_employee.department_id = False

        with freeze_time(
            self.hr_employee.date_version
            + relativedelta(months=self.duration_after_recruitment)
        ):
            self.env["res.company"]._run_employee_appraisal_plans()
            appraisals = self.HrAppraisal.search(
                [("employee_id", "=", self.hr_employee.id)]
            )
            self.assertEqual(appraisals.appraisal_template_id, test_template)
