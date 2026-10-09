from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestWebsiteStudioControllers(HttpCase):
    def test_create_form_page_and_discover_it(self):
        self.authenticate("admin", "admin")
        url = self.call_jsonrpc(
            "/website_studio/create_form", {"res_model": "res.partner"}
        )
        self.assertTrue(url.startswith("/"))

        model = self.env["ir.model"]._get("res.partner")
        self.assertTrue(model.website_form_access)
        self.assertTrue(model.website_form_label)

        page = self.env["website.page"].search([("url", "=", url)], limit=1)
        self.assertTrue(page, "The form page should have been created")
        self.assertIn('data-model_name="res.partner"', page.view_id.arch)
        self.assertIn('name="name"', page.view_id.arch)

        forms = self.call_jsonrpc(
            "/website_studio/get_forms", {"res_model": "res.partner"}
        )
        self.assertIn(url, [form["url"] for form in forms])

    def test_get_forms_without_matching_form(self):
        self.authenticate("admin", "admin")
        forms = self.call_jsonrpc(
            "/website_studio/get_forms", {"res_model": "res.currency"}
        )
        self.assertEqual(forms, [])

    def test_get_website_pages_listing(self):
        self.authenticate("admin", "admin")
        view = self.env["ir.ui.view"].create(
            {
                "name": "Partner Listing",
                "type": "qweb",
                "arch": "<div/>",
                "key": "website_studio.test_partner_listing",
            }
        )
        page = self.env["website.controller.page"].create(
            {
                "name": "Partners",
                "view_id": view.id,
                "model_id": self.env["ir.model"]._get_id("res.partner"),
            }
        )

        result = self.call_jsonrpc(
            "/website_studio/get_website_pages", {"res_model": "res.partner"}
        )
        self.assertEqual([p["id"] for p in result["pages"]], [page.id])
        self.assertEqual(result["pages"][0]["name_slugified"], "partners")
        self.assertTrue(result["websites"])
        self.assertIn("display_name", result["websites"][0])

        other = self.call_jsonrpc(
            "/website_studio/get_website_pages", {"res_model": "res.company"}
        )
        self.assertEqual(other["pages"], [], "pages of other models stay out")

    def test_listing_search_in_place(self):
        self.env["res.partner"].create([{"name": "PN Ada"}, {"name": "PN Grace"}])
        page = (
            self.env["website.controller.page"]
            .with_context({"website_studio.create_page": True})
            .create(
                {
                    "name": "PN Partners",
                    "name_slugified": "pn-partners",
                    "model_id": self.env["ir.model"]._get_id("res.partner"),
                    "record_domain": "[('name', 'ilike', 'PN ')]",
                    "is_published": True,
                }
            )
        )
        self.start_tour(
            f"/model/{page.name_slugified}",
            "website_studio_listing_partial_navigation",
            login="admin",
        )
