from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged, users
from odoo.tests.common import TransactionCase

from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install")
class TestAppraisalPublicAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Relative, not absolute: `_check_next_appraisal_date` rejects a date in
        # the past, so hardcoded years gave the suite an expiry date.
        cls.next_a = date.today() + relativedelta(years=30)
        cls.next_b = cls.next_a + relativedelta(years=1)
        cls.next_c = cls.next_a + relativedelta(years=2)
        cls.company = cls.env["res.company"].create({"name": "mami rock"})
        cls.user_without_hr_right = mail_new_test_user(
            cls.env,
            name="user_without_hr_right",
            login="user_without_hr_right",
            email="user_without_hr_right@example.com",
            groups="base.group_user",
            notification_type="email",
            company_id=cls.company.id,
        )

        cls.manager = cls.env["hr.employee"].create(
            {
                "name": "Johnny",
                "user_id": cls.user_without_hr_right.id,
                "company_id": cls.company.id,
            }
        )

        cls.employee_a, cls.employee_b = cls.env["hr.employee"].create(
            [
                {
                    "name": "David",
                    "parent_id": cls.manager.id,
                    "company_id": cls.company.id,
                    "wage": 1,
                    "contract_date_start": "2017-12-05",
                    "next_appraisal_date": cls.next_a,
                },
                {
                    "name": "Laura",
                    "company_id": cls.company.id,
                    "wage": 1,
                    "contract_date_start": "2018-12-05",
                    "next_appraisal_date": cls.next_b,
                },
            ]
        )
        cls.employee_c = cls.env["hr.employee"].create(
            {
                "name": "Jade",
                "parent_id": cls.employee_a.id,
                "company_id": cls.company.id,
                "wage": 1,
                "contract_date_start": "2019-12-05",
                "next_appraisal_date": cls.next_c,
            }
        )

    def test_manager(self):
        with self.with_user(self.user_without_hr_right.login):
            david, laura, jade = self.env["hr.employee"].browse(
                (self.employee_a | self.employee_b | self.employee_c).ids
            )

            self.assertTrue(david.is_manager)
            self.assertFalse(laura.is_manager)
            self.assertTrue(jade.is_manager)

    def test_manager_access_read(self):
        with self.with_user(self.user_without_hr_right.login):
            david, laura, jade = self.env["hr.employee"].browse(
                (self.employee_a | self.employee_b | self.employee_c).ids
            )

            # Should be able to read direct reports and indirect reports birthday_public_display_string
            self.assertEqual(david.accessible_next_appraisal_date, self.next_a)
            self.assertEqual(jade.accessible_next_appraisal_date, self.next_c)
            # Cannot read values of "manager only field" on an employee the user is not manager of
            self.assertFalse(laura.accessible_next_appraisal_date)

    def test_manager_access_search(self):
        with self.with_user(self.user_without_hr_right.login):
            employees = self.env["hr.employee"].search(
                [("accessible_next_appraisal_date", ">=", self.next_a)]
            )

            # Should not find Laura as the user is not her manager
            self.assertEqual(len(employees), 2)
            self.assertTrue("Laura" not in employees.mapped("name"))

    def test_raw_field_is_hr_only(self):
        # The raw field lives behind hr.group_hr_user: a non-HR read must be
        # refused by the ORM even with the value already in the transaction
        # cache from a privileged read (the warm-cache leak of audit row E02),
        # and grouping by it must be refused too (the read_group leak of E04).
        laura = self.employee_b
        # privileged prewarm of the shared transaction cache
        self.assertEqual(laura.next_appraisal_date, self.next_b)
        with self.with_user(self.user_without_hr_right.login):
            laura_as_manager = self.env["hr.employee"].browse(laura.id)
            with self.assertRaises(AccessError):
                laura_as_manager.read(["next_appraisal_date"])
            with self.assertRaises(AccessError):
                self.env["hr.employee"].read_group(
                    [], ["__count"], ["next_appraisal_date:day"]
                )

    def test_mask_does_not_poison_privileged_reads(self):
        # The masked value and the raw value live in different fields, so a
        # restricted read must not overwrite what a privileged reader sees in
        # the same transaction (the cache poisoning of audit row E03).
        laura = self.employee_b
        with self.with_user(self.user_without_hr_right.login):
            laura_as_manager = self.env["hr.employee"].browse(laura.id)
            self.assertFalse(laura_as_manager.accessible_next_appraisal_date)
        self.assertEqual(laura.next_appraisal_date, self.next_b)

    @users("user_without_hr_right")
    def test_appraisal_flow_without_hr_right(self):
        appraisal = self.env["hr.appraisal"].create(
            {
                "employee_id": self.employee_a.id,
                "manager_ids": self.env.user.employee_ids.ids,
            }
        )
        # A manager without hr right should be able to confirm an appraisal of one of his subordinate
        appraisal.action_confirm()
        self.assertEqual(appraisal.state, "2_pending")

        # An unrated appraisal must not be transitioned, and must say why.
        result = appraisal.action_done()
        self.assertEqual(appraisal.state, "2_pending")
        self.assertEqual(result["params"]["type"], "danger")

        # A manager without hr right should be able to mark as done an appraisal of one of his subordinate
        appraisal.accessible_assessment_note = (
            self.env["hr.appraisal.note"]
            .sudo()
            .search([("company_id", "=", self.company.id)], limit=1)
        )
        self.assertFalse(appraisal.action_done())
        self.assertEqual(appraisal.state, "3_done")

    @users("user_without_hr_right")
    def test_buttons_display_follows_state_in_the_same_transaction(self):
        # `_compute_buttons_display` reads `state`, so `state` must be in its
        # depends. When it was not, a `state` write earlier in the transaction
        # left `can_see_employee_publish` stale at True and the inverse of
        # `accessible_employee_feedback` accepted a write that must be refused.
        appraisal = (
            self.env["hr.appraisal"]
            .sudo()
            .create(
                {
                    "employee_id": self.employee_a.id,
                    "manager_ids": self.manager.ids,
                    "employee_feedback": "<p>written by the appraisee</p>",
                    "employee_feedback_published": False,
                    "state": "1_new",
                }
            )
        )
        appraisal = appraisal.with_user(self.env.user)
        appraisal.invalidate_recordset()
        self.assertTrue(
            appraisal.can_see_employee_publish,
            "the manager may edit the feedback while the appraisal is new",
        )

        # No explicit invalidation: the depends must do the work.
        appraisal.sudo().write({"state": "3_done"})
        self.assertEqual(appraisal.state, "3_done")
        self.assertFalse(
            appraisal.can_see_employee_publish,
            "the flag must follow the state change without an invalidation",
        )
        # `write` publishes both feedbacks on the transition to 3_done, so the
        # text being readable here is by design; what must not survive is the
        # manager's right to CHANGE it.
        with self.assertRaises(UserError):
            appraisal.write({"accessible_employee_feedback": "<p>overwritten</p>"})
        self.assertEqual(
            appraisal.sudo().employee_feedback,
            "<p>written by the appraisee</p>",
            "the appraisee's feedback must survive the refused write",
        )

    def test_is_manager_with_employees_in_several_companies(self):
        # `_compute_user_manager_rights` used `recordset in recordset`, which is
        # `len(item) == 1 and item.id in self._ids`. A user holding an employee
        # record in a second company — which `_user_uniq`, unique on
        # (user_id, company_id), allows — therefore read `is_manager = False`
        # on their own direct report's appraisal and lost every button.
        appraisal = self.env["hr.appraisal"].create({"employee_id": self.employee_a.id})
        self.assertEqual(appraisal.employee_id.parent_id, self.manager)

        other_company = self.env["res.company"].create({"name": "mami paper"})
        self.user_without_hr_right.write({"company_ids": [(4, other_company.id)]})
        self.env["hr.employee"].create(
            {
                "name": "Johnny elsewhere",
                "user_id": self.user_without_hr_right.id,
                "company_id": other_company.id,
            }
        )

        with self.with_user(self.user_without_hr_right.login):
            # `res.users.employee_ids` is scoped by `allowed_company_ids`, so
            # both records are only visible with both companies enabled — which
            # is exactly what the multi-company user does in the interface.
            user = self.env.user.with_context(
                allowed_company_ids=self.env.user.company_ids.ids
            )
            self.env.invalidate_all()
            self.assertEqual(
                len(user.employee_ids),
                2,
                "the fixture must give the user an employee in each company",
            )
            self.assertTrue(
                appraisal.with_env(user.env).browse(appraisal.id).is_manager,
                "a second employee record must not strip the line manager's rights",
            )

    def test_show_feedback_full_follows_the_employee_user_link(self):
        # `_compute_show_employee_feedback_full` reads `employee_id.user_id`
        # but declared only `employee_id`, so linking an employee record to a
        # user in the same transaction left the flag stale.
        # `employee_feedback_published` must be set False explicitly: it
        # defaults to True, which forces the flag to False whatever the user is
        # and would make this test pass for the wrong reason.
        # The reader is a *fresh* user, because `_user_uniq` is unique on
        # (user_id, company_id) and `self.manager` already holds that pair.
        reader = mail_new_test_user(
            self.env,
            name="appraisee",
            login="appraisee",
            email="appraisee@example.com",
            groups="base.group_user",
            notification_type="email",
            company_id=self.company.id,
        )
        employee = self.env["hr.employee"].create(
            {"name": "Unlinked", "company_id": self.company.id}
        )
        appraisal = self.env["hr.appraisal"].create(
            {"employee_id": employee.id, "employee_feedback_published": False}
        )

        with self.with_user(reader.login):
            # `self.env` is the acting user's; `appraisal` still carries the
            # admin env, so it must be re-browsed rather than reused.
            own = self.env["hr.appraisal"].browse(appraisal.id)
            self.assertFalse(own.show_employee_feedback_full)

            employee.sudo().user_id = reader
            self.assertTrue(
                own.show_employee_feedback_full,
                "linking the employee to the reader must reveal their own feedback",
            )
