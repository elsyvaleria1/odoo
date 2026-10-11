from odoo.tests import tagged

from odoo.addons.payment.tests.common import PaymentCommon


@tagged("-at_install", "post_install")
class TestResCompany(PaymentCommon):
    def test_creating_company_duplicates_providers(self):
        main_company = self.env.company
        main_company_providers_count = self.env["payment.provider"].search_count(
            [
                ("company_id", "=", main_company.id),
                ("module_state", "=", "installed"),
            ]
        )

        new_company = self.env["res.company"].create({"name": "New Company"})
        new_company_providers_count = self.env["payment.provider"].search_count(
            [
                ("company_id", "=", new_company.id),
                ("module_state", "=", "installed"),
            ]
        )

        self.assertEqual(new_company_providers_count, main_company_providers_count)

    def test_creating_company_without_custom_mode_in_registry(self):
        company = self.env["res.company"].create({"name": "No Custom Mode Company"})
        self.assertTrue(company.exists())
