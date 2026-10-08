from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestFsmPortalSignUrl(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        project = cls.env["project.project"].create(
            {
                "name": "Field Service to sign",
                "is_fsm": True,
                "allow_timesheets": True,
                "company_id": cls.env.company.id,
            }
        )
        customer = cls.env["res.partner"].create({"name": "Signing customer"})
        cls.task = cls.env["project.task"].create(
            {
                "name": "Report to sign",
                "project_id": project.id,
                "partner_id": customer.id,
            }
        )
        employee = cls.env["hr.employee"].create({"name": "Technician"})
        cls.env["account.analytic.line"].create(
            {
                "name": "Repair",
                "task_id": cls.task.id,
                "project_id": project.id,
                "employee_id": employee.id,
                "unit_amount": 1.0,
            }
        )
        cls.token = cls.task._portal_get_or_create_token()

    def _sign_page(self, query=""):
        self.authenticate(None, None)
        response = self.url_open(
            f"/my/tasks/{self.task.id}?access_token={self.token}{query}"
        )
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_a_page_opened_from_a_mail_signs_through_the_fsm_route(self):
        self.assertTrue(self.task._has_to_be_signed())
        page = self._sign_page()
        self.assertIn(f"/my/tasks/{self.task.id}/worksheet/sign/fsm", page)
        self.assertNotIn("/worksheet/sign/None", page)

    def test_the_source_a_preview_names_is_kept_and_any_other_ignored(self):
        self.assertIn("/worksheet/sign/project", self._sign_page("&source=project"))
        self.assertIn("/worksheet/sign/fsm", self._sign_page("&source=elsewhere"))
