import odoo.tests
from odoo.tools import mute_logger


@odoo.tests.common.tagged("post_install", "-at_install")
class TestWebsiteError(odoo.tests.HttpCase):
    @mute_logger("odoo.addons.http_routing.models.ir_http", "odoo.http")
    def test_01_run_test(self):
        self.start_tour("/test_error_view", "test_error_website")


@odoo.tests.common.tagged("post_install", "-at_install")
class TestErrorPageOffWebsite(odoo.tests.HttpCase):
    def test_a_route_off_the_website_answers_its_error_page(self):
        self.authenticate("admin", "admin")
        response = self.url_open("/test_off_website_refusal", allow_redirects=False)
        self.assertEqual(response.status_code, 403)
        self.assertIn("A route off the website refused this request.", response.text)
        self.assertIn(
            "data-website-id=",
            response.text,
            "the page must be the website's error page, whose layout reads the "
            "website a website=False request does not carry",
        )
