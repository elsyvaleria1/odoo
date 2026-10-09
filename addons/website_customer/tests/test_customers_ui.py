from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestCustomersUi(HttpCase):
    def test_customers_search_in_place(self):
        implementer = self.env["res.partner"].create({"name": "PN Implementer"})
        self.env["res.partner"].create(
            [
                {
                    "name": name,
                    "is_published": True,
                    "assigned_partner_id": implementer.id,
                }
                for name in ("PN Acme", "PN Globex")
            ]
        )
        self.start_tour("/customers", "customers_partial_navigation")
