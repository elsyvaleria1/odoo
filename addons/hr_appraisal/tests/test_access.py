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

            self.assertEqual(david.accessible_next_appraisal_date, self.next_a)
            self.assertEqual(jade.accessible_next_appraisal_date, self.next_c)
            self.assertFalse(laura.accessible_next_appraisal_date)

    def test_manager_access_search(self):
        with self.with_user(self.user_without_hr_right.login):
            employees = self.env["hr.employee"].search(
                [("accessible_next_appraisal_date", ">=", self.next_a)]
            )

            self.assertEqual(len(employees), 2)
            self.assertTrue("Laura" not in employees.mapped("name"))

    def test_raw_field_is_hr_only(self):
        laura = self.employee_b
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
        appraisal.action_confirm()
        self.assertEqual(appraisal.state, "2_pending")

        result = appraisal.action_done()
        self.assertEqual(appraisal.state, "2_pending")
        self.assertEqual(result["params"]["type"], "danger")

        appraisal.accessible_assessment_note = (
            self.env["hr.appraisal.note"]
            .sudo()
            .search([("company_id", "=", self.company.id)], limit=1)
        )
        self.assertFalse(appraisal.action_done())
        self.assertEqual(appraisal.state, "3_done")

    @users("user_without_hr_right")
    def test_buttons_display_follows_state_in_the_same_transaction(self):
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

        appraisal.sudo().write({"state": "3_done"})
        self.assertEqual(appraisal.state, "3_done")
        self.assertFalse(
            appraisal.can_see_employee_publish,
            "the flag must follow the state change without an invalidation",
        )
        with self.assertRaises(UserError):
            appraisal.write({"accessible_employee_feedback": "<p>overwritten</p>"})
        self.assertEqual(
            appraisal.sudo().employee_feedback,
            "<p>written by the appraisee</p>",
            "the appraisee's feedback must survive the refused write",
        )

    def test_is_manager_with_employees_in_several_companies(self):
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
            own = self.env["hr.appraisal"].browse(appraisal.id)
            self.assertFalse(own.show_employee_feedback_full)

            employee.sudo().user_id = reader
            self.assertTrue(
                own.show_employee_feedback_full,
                "linking the employee to the reader must reveal their own feedback",
            )
