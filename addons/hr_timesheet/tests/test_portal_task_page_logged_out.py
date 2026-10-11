from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPortalTaskPageLoggedOut(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env["project.project"].create(
            {
                "name": "Logged-out timesheets",
                "privacy_visibility": "portal",
                "allow_timesheets": True,
            }
        )
        cls.task = cls.env["project.task"].create(
            {"name": "Logged-out task page", "project_id": project.id}
        )
        cls.token = cls.task._portal_get_or_create_token()

    def test_a_link_holder_who_is_logged_out_opens_the_task_page(self):
        self.authenticate(None, None)
        response = self.url_open(f"/my/tasks/{self.task.id}?access_token={self.token}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.task.name, response.text)

    def test_the_public_user_reads_the_company_encoding_unit(self):
        public = self.env.ref("base.public_user")
        Line = self.env["account.analytic.line"].with_user(public)
        self.env.company.hr_timesheet_config_id.timesheet_encode_uom_id = self.env.ref(
            "base.product_uom_day"
        )
        self.env.invalidate_all()
        self.assertTrue(Line._is_timesheet_encode_uom_day())
        self.env.company.hr_timesheet_config_id.timesheet_encode_uom_id = self.env.ref(
            "base.product_uom_hour"
        )
        self.env.invalidate_all()
        self.assertFalse(Line._is_timesheet_encode_uom_day())
