from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWizardCompany(TransactionCase):
    def test_the_location_is_offered_from_the_employee_company(self):
        wizard = self.env["wizard.hr.employee.update.work.location"]
        with self.assertNoLogs("odoo.fields", "WARNING"):
            domain = wizard.fields_get(["work_location_id"], ["domain"])[
                "work_location_id"
            ]["domain"]
        self.assertIn("company_id", domain)
